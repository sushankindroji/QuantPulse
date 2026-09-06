"""
Backtest orchestration.

    Market -> Regime detection -> Signal evaluation -> Regime-specific
    weighting -> Risk constraints -> Desired position -> Execution -> PnL

This ties together features.py, signals.py, regimes.py, evaluation.py,
risk.py and execution.py into one reproducible run, and is what the
experiment tracker records.

REGIME CAUSALITY:
    Regime labels are fitted on the train slice and applied to the test
    slice via regimes.fit_regimes() + regimes.apply_regimes().  The regime
    model therefore only uses information available before the test period
    starts, eliminating look-ahead bias in regime-conditional IC breakdowns.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.config import ExecutionAssumptions, RiskLimits
from app.domain import evaluation as ev
from app.domain.features import build_feature_matrix
from app.domain import execution as ex
from app.domain import regimes as rg
from app.domain import risk as rk
from app.domain.signals import DEFAULT_SIGNALS, AlphaSignal


@dataclass
class SignalReport:
    name: str
    ic: ev.ICResult
    decay: pd.DataFrame
    ic_by_regime: pd.DataFrame | None = None


@dataclass
class BacktestResult:
    signal_reports: list[SignalReport]
    combined_score: pd.Series
    positions: pd.Series
    gross_returns: pd.Series
    net_returns: pd.Series
    risk_report: dict
    cost_sensitivity: pd.DataFrame
    regime_result: rg.RegimeResult | None


def evaluate_signals(
    full: pd.DataFrame,
    horizon: int,
    signals: list[AlphaSignal] = None,
    regime_labels: pd.Series | None = None,
) -> list[SignalReport]:
    signals = signals or DEFAULT_SIGNALS
    horizons = tuple(sorted({int(c.split("_")[-1]) for c in full.columns if c.startswith("future_return_")}))
    target_col = f"future_return_{horizon}"
    reports = []
    for sig in signals:
        if not sig.check_available(full):
            continue
        score = sig.score(full)
        ic = ev.information_coefficient(score, full[target_col])
        decay = ev.alpha_decay(score, full, horizons)
        regime_ic = ev.ic_by_regime(score, full[target_col], regime_labels) if regime_labels is not None else None
        reports.append(SignalReport(name=sig.meta.name, ic=ic, decay=decay, ic_by_regime=regime_ic))
    return reports


def combine_signals(full: pd.DataFrame, signals: list[AlphaSignal], reports: list[SignalReport]) -> pd.Series:
    """IC-weighted signal combination: signals with stronger, more
    significant (out-of-sample-estimated) IC get more weight. Signals with
    non-significant or negative IC receive ~zero weight."""
    weights = {}
    for r in reports:
        if r.ic.significant_at_5pct and not np.isnan(r.ic.ic):
            weights[r.name] = max(r.ic.ic, 0.0)
        else:
            weights[r.name] = 0.0
    total = sum(weights.values())
    scored = pd.DataFrame(index=full.index)
    for sig in signals:
        if sig.meta.name in weights and sig.check_available(full):
            scored[sig.meta.name] = sig.score(full)
    if total <= 0:
        # no signal cleared significance -- flat combined score, reported honestly
        return pd.Series(0.0, index=full.index)
    combined = sum(scored[name] * (w / total) for name, w in weights.items() if name in scored)
    return combined


def run_backtest(
    df: pd.DataFrame,
    full: pd.DataFrame,
    horizon: int,
    exec_cfg: ExecutionAssumptions,
    risk_cfg: RiskLimits,
    use_regimes: bool = True,
    signals: list[AlphaSignal] = None,
    train_df: pd.DataFrame | None = None,
) -> BacktestResult:
    """Run a single-fold backtest.

    Parameters
    ----------
    df : raw OHLCV for the test period (used for price and regime context).
    full : feature matrix for the test period.
    horizon : forward-return horizon for signal evaluation.
    exec_cfg : execution cost assumptions.
    risk_cfg : risk limits.
    use_regimes : whether to compute regime-conditional IC breakdowns.
    signals : list of AlphaSignal objects (defaults to DEFAULT_SIGNALS).
    train_df : raw OHLCV for the train period.  When provided, the regime
        model is fitted on train_df and applied to df (causal).  When None,
        the model is fitted on df itself (non-causal, kept for backward
        compatibility with tests and exploratory use).
    """
    signals = signals or DEFAULT_SIGNALS

    regime_result = None
    regime_labels = None
    if use_regimes:
        if train_df is not None and len(train_df) >= 50:
            # Causal path: fit on train, apply to test — no look-ahead.
            fitted_model = rg.fit_regimes(train_df)
            regime_result = rg.apply_regimes(fitted_model, df.loc[full.index[0] : full.index[-1]])
        else:
            # Non-causal fallback (exploratory / unit tests without train_df).
            # This is documented as look-ahead and clearly flagged in the result.
            regime_result = rg.detect_regimes(df.loc[full.index[0] : full.index[-1]])
        regime_labels = regime_result.labels.reindex(full.index)

    # Signal weights must be estimated from the training period. Using the
    # test-period IC to choose weights would leak the answer into the trading
    # rule and make the reported out-of-sample result optimistic.
    reports = evaluate_signals(full, horizon, signals, regime_labels)
    if train_df is not None and len(train_df) >= 50:
        train_full = build_feature_matrix(train_df)
        train_reports = evaluate_signals(train_full, horizon, signals)
        combined_score = combine_signals(full, signals, train_reports)
    else:
        # Exploratory/unit-test path: no train data is available, so preserve
        # the historical behavior rather than pretending the result is causal.
        combined_score = combine_signals(full, signals, reports)

    realized_vol = full.get("realized_vol_20", pd.Series(np.nan, index=full.index)).reindex(full.index)
    desired_position = rk.volatility_target_position(
        combined_score, realized_vol, risk_cfg.target_annual_vol, max_position=risk_cfg.max_position
    )

    price = df["close"].reindex(full.index)
    exec_result = ex.simulate_execution(desired_position, price, exec_cfg)

    positions = rk.apply_drawdown_stop(exec_result.net_returns, exec_result.positions, risk_cfg.max_drawdown_stop)
    # Recompute PnL with drawdown-stopped positions for final reporting.
    bar_return = price.pct_change().fillna(0.0)
    final_gross = positions.shift(1).fillna(0.0) * bar_return
    per_unit_cost = (exec_cfg.spread_pips + exec_cfg.slippage_pips) * exec_cfg.pip_size / price
    final_turnover = positions.diff().abs().fillna(positions.abs())
    final_costs = final_turnover * per_unit_cost.fillna(0.0)
    final_net = final_gross - final_costs

    risk_report = rk.full_risk_report(final_net, positions)
    cost_sensitivity = ex.cost_sensitivity_curve(desired_position, price, exec_cfg)

    return BacktestResult(
        signal_reports=reports,
        combined_score=combined_score,
        positions=positions,
        gross_returns=final_gross,
        net_returns=final_net,
        risk_report=risk_report,
        cost_sensitivity=cost_sensitivity,
        regime_result=regime_result,
    )
