import numpy as np
import pandas as pd

from app.domain.evaluation import (
    alpha_decay,
    bootstrap_ci,
    ic_by_regime,
    information_coefficient,
    multiple_testing_correction,
    sharpe_significance,
)
from app.domain.signals import DEFAULT_SIGNALS, MeanReversionSignal, MomentumSignal


def test_all_default_signals_produce_bounded_scores(full_features):
    for sig in DEFAULT_SIGNALS:
        if not sig.check_available(full_features):
            continue
        score = sig.score(full_features)
        assert score.between(-1.001, 1.001).all(), sig.meta.name


def test_signal_metadata_present():
    for sig in DEFAULT_SIGNALS:
        assert sig.meta.name
        assert sig.meta.required_features
        assert sig.meta.expected_horizon > 0


def test_information_coefficient_perfect_correlation():
    idx = pd.date_range("2024-01-01", periods=200, freq="h")
    x = pd.Series(np.arange(200), index=idx, dtype=float)
    y = x * 2 + 1  # perfectly monotonic -> Spearman IC == 1
    res = information_coefficient(x, y)
    assert res.ic == pytest_approx(1.0)
    assert res.significant_at_5pct


def test_information_coefficient_insufficient_data_returns_nan():
    idx = pd.date_range("2024-01-01", periods=5, freq="h")
    x = pd.Series(range(5), index=idx, dtype=float)
    y = pd.Series(range(5), index=idx, dtype=float)
    res = information_coefficient(x, y)
    assert np.isnan(res.ic)
    assert res.significant_at_5pct is False


def test_alpha_decay_returns_all_horizons(full_features):
    sig = MomentumSignal(20)
    score = sig.score(full_features)
    decay = alpha_decay(score, full_features, horizons=(1, 5, 10, 20))
    assert set(decay["horizon"]) == {1, 5, 10, 20}


def test_ic_by_regime_groups_correctly(full_features):
    idx = full_features.index
    regime = pd.Series(np.where(np.arange(len(idx)) % 2 == 0, "regime_a", "regime_b"), index=idx)
    sig = MeanReversionSignal(20)
    score = sig.score(full_features)
    result = ic_by_regime(score, full_features["future_return_5"], regime)
    assert set(result["regime"]) == {"regime_a", "regime_b"}


def test_bootstrap_ci_contains_mean():
    values = np.array([0.01, 0.02, -0.01, 0.015, 0.005, -0.005] * 20)
    mean, lo, hi = bootstrap_ci(values, n_boot=500)
    assert lo <= mean <= hi


def test_sharpe_significance_keys():
    r = pd.Series(np.random.default_rng(1).normal(0.001, 0.01, 300))
    result = sharpe_significance(r)
    assert set(result.keys()) == {"sharpe", "t_stat", "p_value", "n"}


def test_multiple_testing_correction_increases_pvalues():
    raw = [0.01, 0.02, 0.03]
    corrected = multiple_testing_correction(raw)
    assert all(c >= r for c, r in zip(corrected, raw))


def pytest_approx(value, tol=1e-6):
    class _Approx:
        def __eq__(self, other):
            return abs(other - value) < tol

    return _Approx()
