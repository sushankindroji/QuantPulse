from app.domain.regimes import apply_regimes, detect_regimes, fit_regimes


def test_detect_regimes_returns_probabilities_summing_to_one(demo_df):
    result = detect_regimes(demo_df, n_regimes=4)
    sums = result.probabilities.sum(axis=1)
    assert (sums.round(6) == 1.0).all()


def test_detect_regimes_labels_align_with_probabilities(demo_df):
    result = detect_regimes(demo_df, n_regimes=4)
    assert len(result.labels) == len(result.probabilities)
    assert result.method in ("hmm", "gmm_fallback")


def test_regime_names_are_interpretable(demo_df):
    result = detect_regimes(demo_df, n_regimes=4)
    valid_prefixes = ("trend_up", "trend_down", "mean_revert", "high_vol")
    for name in result.regime_names.values():
        assert name in valid_prefixes


def test_detect_regimes_non_causal_flag(demo_df):
    result = detect_regimes(demo_df, n_regimes=4)
    assert result.causal is False


def test_fit_apply_regimes_causal(demo_df):
    """fit_regimes + apply_regimes gives causal labels: model is trained on
    a train slice and applied to a held-out test slice without look-ahead."""
    n = len(demo_df)
    train = demo_df.iloc[: n // 2]
    test = demo_df.iloc[n // 2 :]

    fitted = fit_regimes(train, n_regimes=4)
    result = apply_regimes(fitted, test)

    assert result.causal is True
    assert result.method in ("hmm", "gmm_fallback")
    assert len(result.labels) == len(result.probabilities)
    sums = result.probabilities.sum(axis=1)
    assert (sums.round(6) == 1.0).all()
    valid = ("trend_up", "trend_down", "mean_revert", "high_vol")
    for name in result.regime_names.values():
        assert name in valid
