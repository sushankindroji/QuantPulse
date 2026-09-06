import numpy as np
import pandas as pd

from app.domain.features import build_feature_matrix, feature_columns, target_column


def test_feature_matrix_has_no_nans(full_features):
    assert not full_features.isna().any().any()


def test_no_future_columns_among_features(full_features):
    feats = feature_columns(full_features)
    assert all(not c.startswith("future_") for c in feats)


def test_target_columns_exist(full_features):
    for h in (1, 5, 10, 20):
        assert target_column(h) in full_features.columns


def test_features_use_only_past_information(demo_df):
    """Truncating the dataframe at time t must not change any feature value
    computed at any time <= t - lookback. We test this by recomputing
    features on a truncated series and comparing overlapping, fully-warmed
    rows to the full computation."""
    full = build_feature_matrix(demo_df, horizons=(1,), dropna=False)
    truncated_df = demo_df.iloc[: len(demo_df) - 100]
    truncated_full = build_feature_matrix(truncated_df, horizons=(1,), dropna=False)

    common_index = truncated_full.index[100:]  # skip warm-up window
    feats = feature_columns(full)
    a = full.loc[common_index, feats]
    b = truncated_full.loc[common_index, feats]
    pd.testing.assert_frame_equal(a, b, check_exact=False, atol=1e-9)


def test_future_return_matches_manual_calc(demo_df):
    full = build_feature_matrix(demo_df, horizons=(5,), dropna=False)
    log_close = np.log(demo_df["close"])
    expected = log_close.shift(-5) - log_close
    pd.testing.assert_series_equal(
        full["future_return_5"], expected.rename("future_return_5"), check_exact=False, atol=1e-12
    )
