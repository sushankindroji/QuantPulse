import numpy as np
import pandas as pd

from app.config import ExecutionAssumptions
from app.domain.execution import cost_sensitivity_curve, simulate_execution


def _sample_price(n=300, seed=1):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, 0.001, n)
    price = 1.7 * np.exp(np.cumsum(rets))
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.Series(price, index=idx)


def test_zero_cost_net_equals_gross():
    price = _sample_price()
    position = pd.Series(1.0, index=price.index)
    cfg = ExecutionAssumptions(spread_pips=0, slippage_pips=0, commission_per_lot=0, latency_bars=0)
    result = simulate_execution(position, price, cfg)
    pd.testing.assert_series_equal(result.gross_returns, result.net_returns, check_names=False)


def test_costs_reduce_net_returns_when_trading():
    price = _sample_price()
    rng = np.random.default_rng(0)
    position = pd.Series(rng.choice([-1, 0, 1], size=len(price)), index=price.index).astype(float)
    cfg = ExecutionAssumptions(spread_pips=2.0, slippage_pips=1.0, latency_bars=1)
    result = simulate_execution(position, price, cfg)
    assert result.net_returns.sum() <= result.gross_returns.sum()
    assert (result.costs >= 0).all()


def test_latency_delays_position():
    price = _sample_price()
    position = pd.Series(0.0, index=price.index)
    position.iloc[10] = 1.0
    cfg = ExecutionAssumptions(latency_bars=3, spread_pips=0, slippage_pips=0)
    result = simulate_execution(position, price, cfg)
    assert result.positions.iloc[13] == 1.0
    assert result.positions.iloc[10] == 0.0


def test_position_respects_max_position_cap():
    price = _sample_price()
    position = pd.Series(5.0, index=price.index)  # way over the cap
    cfg = ExecutionAssumptions(max_position=1.0)
    result = simulate_execution(position, price, cfg)
    assert result.positions.abs().max() <= 1.0


def test_cost_sensitivity_curve_monotonic_drag():
    price = _sample_price()
    rng = np.random.default_rng(2)
    position = pd.Series(rng.choice([-1, 1], size=len(price)), index=price.index).astype(float)
    cfg = ExecutionAssumptions(spread_pips=1.0, slippage_pips=0.5)
    curve = cost_sensitivity_curve(position, price, cfg, stress_multipliers=(0.0, 1.0, 2.0))
    drags = curve.sort_values("cost_multiplier")["total_cost_drag"].values
    assert (np.diff(drags) >= -1e-12).all()  # cost drag should not decrease as stress increases
