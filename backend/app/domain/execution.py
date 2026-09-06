"""
Execution model.

The backtester must NOT assume signal -> immediate fill at close price.
This module turns a desired-position series into realized PnL by explicitly
modeling: latency (fill delay), spread cost, slippage, and commissions.
Everything is configurable via `ExecutionAssumptions` (see config.py).

Pipeline (per spec section 26):
    signal -> desired position -> order -> spread -> slippage ->
    transaction costs -> latency -> execution -> actual position -> PnL
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.config import ExecutionAssumptions


@dataclass
class ExecutionResult:
    positions: pd.Series          # actual (delayed) position held each bar
    gross_returns: pd.Series
    net_returns: pd.Series
    costs: pd.Series              # cost drag per bar, in return units
    turnover: pd.Series


def simulate_execution(
    desired_position: pd.Series,
    price: pd.Series,
    exec_cfg: ExecutionAssumptions,
) -> ExecutionResult:
    """
    desired_position: signal-derived target exposure in [-1, 1] (or scaled),
        indexed identically to `price`.
    price: close price series used to compute bar-over-bar returns.
    """
    desired_position = desired_position.clip(-exec_cfg.max_position, exec_cfg.max_position)

    # Latency: the position you asked for at t is only actually held from
    # t + latency_bars onward.
    actual_position = desired_position.shift(exec_cfg.latency_bars).fillna(0.0)

    bar_return = price.pct_change().fillna(0.0)
    gross_returns = actual_position.shift(1).fillna(0.0) * bar_return

    turnover = actual_position.diff().abs().fillna(actual_position.abs())

    spread_cost_frac = exec_cfg.spread_pips * exec_cfg.pip_size / price
    slippage_cost_frac = exec_cfg.slippage_pips * exec_cfg.pip_size / price
    per_unit_cost = spread_cost_frac + slippage_cost_frac
    commission_frac = exec_cfg.commission_per_lot / price.replace(0, np.nan)

    costs = turnover * (per_unit_cost.fillna(0.0) + commission_frac.fillna(0.0))
    net_returns = gross_returns - costs

    return ExecutionResult(
        positions=actual_position,
        gross_returns=gross_returns,
        net_returns=net_returns,
        costs=costs,
        turnover=turnover,
    )


def cost_sensitivity_curve(
    desired_position: pd.Series,
    price: pd.Series,
    base_cfg: ExecutionAssumptions,
    stress_multipliers: tuple[float, ...] = (0.0, 0.5, 1.0, 2.0, 4.0),
) -> pd.DataFrame:
    """Gross -> after-spread -> after-slippage -> after-cost -> stress table."""
    rows = []
    for mult in stress_multipliers:
        cfg = ExecutionAssumptions(
            spread_pips=base_cfg.spread_pips * mult,
            slippage_pips=base_cfg.slippage_pips * mult,
            commission_per_lot=base_cfg.commission_per_lot * mult,
            latency_bars=base_cfg.latency_bars,
            pip_size=base_cfg.pip_size,
            max_position=base_cfg.max_position,
        )
        res = simulate_execution(desired_position, price, cfg)
        ann_factor = np.sqrt(252)
        gross_sharpe = (
            res.gross_returns.mean() / res.gross_returns.std() * ann_factor
            if res.gross_returns.std() > 0
            else np.nan
        )
        net_sharpe = (
            res.net_returns.mean() / res.net_returns.std() * ann_factor
            if res.net_returns.std() > 0
            else np.nan
        )
        rows.append(
            {
                "cost_multiplier": mult,
                "gross_sharpe": gross_sharpe,
                "net_sharpe": net_sharpe,
                "total_cost_drag": res.costs.sum(),
                "gross_cum_return": res.gross_returns.sum(),
                "net_cum_return": res.net_returns.sum(),
            }
        )
    return pd.DataFrame(rows)
