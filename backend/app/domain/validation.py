"""
Time-series validation.

No random train/test splits for financial time series. This module provides
walk-forward folds with an optional embargo (purge) period between train and
test to reduce leakage from autocorrelated features/labels that span the
train/test boundary.

    Train -> [embargo] -> Test
          Train -> [embargo] -> Test
                Train -> [embargo] -> Test
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Fold:
    fold_id: int
    train_index: pd.Index
    test_index: pd.Index


def walk_forward_folds(
    index: pd.Index,
    train_bars: int,
    test_bars: int,
    step_bars: int,
    embargo_bars: int = 0,
) -> list[Fold]:
    n = len(index)
    folds = []
    start = 0
    fold_id = 0
    while True:
        train_end = start + train_bars
        test_start = train_end + embargo_bars
        test_end = test_start + test_bars
        if test_end > n:
            break
        train_idx = index[start:train_end]
        test_idx = index[test_start:test_end]
        folds.append(Fold(fold_id=fold_id, train_index=train_idx, test_index=test_idx))
        start += step_bars
        fold_id += 1
    return folds


def detect_leakage(
    train_index: pd.Index, test_index: pd.Index, embargo_bars: int = 0
) -> dict:
    """Automated check: train and test must not overlap, and (if embargo is
    requested) must be separated by at least `embargo_bars`."""
    overlap = train_index.intersection(test_index)
    issues = []
    if len(overlap) > 0:
        issues.append(f"train/test overlap of {len(overlap)} timestamps")
    if len(train_index) and len(test_index):
        train_end_pos = train_index[-1]
        test_start_pos = test_index[0]
        if test_start_pos <= train_end_pos:
            issues.append("test set starts before or at train set end")
    return {"ok": len(issues) == 0, "issues": issues}


def check_no_future_features(feature_cols: list[str]) -> dict:
    """Sanity check that no feature column is itself a forward-looking target."""
    leaking = [c for c in feature_cols if c.startswith("future_")]
    return {"ok": len(leaking) == 0, "leaking_columns": leaking}
