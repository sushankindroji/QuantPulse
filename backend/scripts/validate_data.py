#!/usr/bin/env python3
"""
`make validate-data` entrypoint.

Runs the data-quality checks required by the spec: missing timestamps,
duplicates, impossible prices, negative/invalid values, broken ordering,
spread anomalies, and timezone problems.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from app.config import RAW_DIR


def validate(df: pd.DataFrame) -> list[str]:
    issues = []

    if not df.index.is_monotonic_increasing:
        issues.append("timestamp index is not monotonically increasing (broken ordering)")

    if df.index.duplicated().any():
        issues.append(f"{df.index.duplicated().sum()} duplicate timestamps")

    if df.index.tz is None:
        issues.append("timestamp index is not timezone-aware (expected UTC)")

    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            issues.append(f"missing required column: {col}")
            continue
        if (df[col] <= 0).any():
            issues.append(f"{col} has non-positive (impossible) prices")
        if df[col].isna().any():
            issues.append(f"{col} has missing values")

    if {"high", "low"}.issubset(df.columns):
        bad_range = df["high"] < df["low"]
        if bad_range.any():
            issues.append(f"{bad_range.sum()} bars have high < low")

    if "volume" in df.columns and (df["volume"] < 0).any():
        issues.append("negative volume values found")

    # crude spread-anomaly check: bar range vs local median range
    if {"high", "low"}.issubset(df.columns) and len(df) > 50:
        rng = df["high"] - df["low"]
        median_rng = rng.rolling(50, min_periods=10).median()
        anomalies = (rng > median_rng * 20).sum()
        if anomalies > 0:
            issues.append(f"{anomalies} bars have a range >20x the local median (possible bad tick)")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate raw market data quality.")
    parser.add_argument("--instrument", default="GBP_CAD")
    parser.add_argument("--timeframe", default="1h")
    args = parser.parse_args()

    path = RAW_DIR / f"{args.instrument}_{args.timeframe}.parquet"
    if not path.exists():
        print(f"No raw data found at {path}. Run `make download-data` first, "
              "or continue with demo mode via `make run-research`.", file=sys.stderr)
        return 1

    df = pd.read_parquet(path)
    issues = validate(df)
    if issues:
        print(f"Validation FAILED for {path} ({len(issues)} issue(s)):")
        for i in issues:
            print(f"  - {i}")
        return 1

    print(f"Validation PASSED for {path} ({len(df)} bars).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
