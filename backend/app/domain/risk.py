"""Risk engine: position sizing, volatility targeting, and risk metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import RiskLimits


def volatility_target_position(
    raw_signal: pd.Series,
    realized_vol: pd.Series,
    target_annual_vol: float,
    periods_per_year: int = 252,
    max_position: float = 1.0,
) -> pd.Series:
    """Scale a raw [-1,1] signal so the resulting position targets a fixed
    annualized volatility, subject to a hard position cap."""
    target_period_vol = target_annual_vol / np.sqrt(periods_per_year)
    vol = realized_vol.replace(0, np.nan)
    scale = (target_period_vol / vol).clip(upper=max_position * 5)
    position = (raw_signal * scale).clip(-max_position, max_position).fillna(0.0)
    return position


def apply_drawdown_stop(returns: pd.Series, positions: pd.Series, max_drawdown: float) -> pd.Series:
    """Flatten the position once cumulative drawdown breaches the limit,
    until equity recovers above the trough * (1+max_drawdown)."""
    equity = (1 + returns.fillna(0)).cumprod()
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    stopped = drawdown <= -max_drawdown
    adj_positions = positions.copy()
    in_stop = False
    out = []
    for i, is_stop in enumerate(stopped):
        if is_stop:
            in_stop = True
        if in_stop:
            out.append(0.0)
            if not is_stop:
                in_stop = False
        else:
            out.append(adj_positions.iloc[i])
    return pd.Series(out, index=positions.index)


def max_drawdown(returns: pd.Series) -> float:
    equity = (1 + returns.fillna(0)).cumprod()
    running_max = equity.cummax()
    dd = equity / running_max - 1
    return float(dd.min())


def value_at_risk(returns: pd.Series, alpha: float = 0.05) -> float:
    r = returns.dropna()
    if len(r) == 0:
        return np.nan
    return float(-np.percentile(r, alpha * 100))


def expected_shortfall(returns: pd.Series, alpha: float = 0.05) -> float:
    r = returns.dropna()
    if len(r) == 0:
        return np.nan
    var = np.percentile(r, alpha * 100)
    tail = r[r <= var]
    if len(tail) == 0:
        return float(-var)
    return float(-tail.mean())


def sharpe_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    r = returns.dropna()
    if r.std() == 0 or len(r) == 0:
        return np.nan
    return float(r.mean() / r.std() * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    r = returns.dropna()
    downside = r[r < 0]
    if len(downside) == 0 or downside.std() == 0:
        return np.nan
    return float(r.mean() / downside.std() * np.sqrt(periods_per_year))


def profit_factor(returns: pd.Series) -> float:
    r = returns.dropna()
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses == 0:
        return np.nan
    return float(gains / losses)


def hit_rate(returns: pd.Series) -> float:
    r = returns.dropna()
    if len(r) == 0:
        return np.nan
    return float((r > 0).mean())


def full_risk_report(returns: pd.Series, positions: pd.Series | None = None) -> dict:
    report = {
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown": max_drawdown(returns),
        "volatility_annualized": float(returns.std() * np.sqrt(252)) if returns.std() == returns.std() else np.nan,
        "var_95": value_at_risk(returns, 0.05),
        "expected_shortfall_95": expected_shortfall(returns, 0.05),
        "hit_rate": hit_rate(returns),
        "profit_factor": profit_factor(returns),
        "cumulative_return": float((1 + returns.fillna(0)).prod() - 1),
    }
    if positions is not None:
        report["avg_exposure"] = float(positions.abs().mean())
        report["turnover"] = float(positions.diff().abs().sum())
    return report
