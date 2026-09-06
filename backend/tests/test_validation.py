import pandas as pd

from app.domain.validation import (
    check_no_future_features,
    detect_leakage,
    walk_forward_folds,
)


def test_walk_forward_folds_no_overlap(full_features):
    folds = walk_forward_folds(full_features.index, train_bars=500, test_bars=100, step_bars=100, embargo_bars=5)
    assert len(folds) > 0
    for fold in folds:
        leak = detect_leakage(fold.train_index, fold.test_index, embargo_bars=5)
        assert leak["ok"], leak["issues"]


def test_walk_forward_respects_embargo(full_features):
    folds = walk_forward_folds(full_features.index, train_bars=500, test_bars=100, step_bars=100, embargo_bars=10)
    fold = folds[0]
    train_end = fold.train_index[-1]
    test_start = fold.test_index[0]
    gap = full_features.index.get_loc(test_start) - full_features.index.get_loc(train_end)
    assert gap >= 10


def test_no_future_feature_columns_detected():
    good = ["return_5", "zscore_20", "realized_vol_10"]
    bad = ["return_5", "future_return_5"]
    assert check_no_future_features(good)["ok"] is True
    result = check_no_future_features(bad)
    assert result["ok"] is False
    assert "future_return_5" in result["leaking_columns"]


def test_insufficient_data_returns_no_folds():
    idx = pd.date_range("2020-01-01", periods=100, freq="h")
    folds = walk_forward_folds(idx, train_bars=500, test_bars=100, step_bars=100)
    assert folds == []
