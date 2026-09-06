import numpy as np
import pandas as pd

from app.domain.risk import (
    apply_drawdown_stop,
    expected_shortfall,
    full_risk_report,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    value_at_risk,
    volatility_target_position,
)


def test_sharpe_ratio_of_zero_vol_is_nan():
    r = pd.Series([0.0] * 20)
    assert np.isnan(sharpe_ratio(r))


def test_max_drawdown_is_nonpositive():
    r = pd.Series([0.01, -0.05, 0.02, -0.1, 0.03])
    dd = max_drawdown(r)
    assert dd <= 0


def test_var_and_es_es_worse_than_var():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0, 0.01, 5000))
    var = value_at_risk(r, 0.05)
    es = expected_shortfall(r, 0.05)
    assert es >= var  # ES (average of tail) should be at least as extreme as VaR


def test_volatility_target_position_scales_inversely_with_vol():
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    signal = pd.Series([1.0] * 5, index=idx)
    low_vol = pd.Series([0.001] * 5, index=idx)
    high_vol = pd.Series([0.01] * 5, index=idx)
    pos_low = volatility_target_position(signal, low_vol, target_annual_vol=0.1, max_position=10)
    pos_high = volatility_target_position(signal, high_vol, target_annual_vol=0.1, max_position=10)
    assert pos_low.iloc[0] > pos_high.iloc[0]


def test_drawdown_stop_flattens_position():
    idx = pd.date_range("2024-01-01", periods=6, freq="D")
    returns = pd.Series([0.0, -0.1, -0.1, -0.1, 0.0, 0.0], index=idx)
    positions = pd.Series([1.0] * 6, index=idx)
    stopped = apply_drawdown_stop(returns, positions, max_drawdown=0.2)
    assert stopped.iloc[3] == 0.0  # should have stopped out by the 3rd big loss


def test_profit_factor_positive_when_gains_exceed_losses():
    r = pd.Series([0.02, -0.01, 0.03, -0.01])
    pf = profit_factor(r)
    assert pf > 1.0


def test_full_risk_report_has_expected_keys():
    r = pd.Series(np.random.default_rng(0).normal(0.0005, 0.01, 300))
    report = full_risk_report(r)
    for key in ("sharpe", "sortino", "max_drawdown", "var_95", "expected_shortfall_95", "hit_rate"):
        assert key in report
