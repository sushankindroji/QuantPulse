#!/usr/bin/env python3
"""`make prepare-data` entrypoint: clean raw data and write to Parquet for research."""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from app.config import PROCESSED_DIR, RAW_DIR


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    df = df[df["high"] >= df["low"]]
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean raw data and prepare it for research.")
    parser.add_argument("--instrument", default="GBP_CAD")
    parser.add_argument("--timeframe", default="1h")
    args = parser.parse_args()

    raw_path = RAW_DIR / f"{args.instrument}_{args.timeframe}.parquet"
    if not raw_path.exists():
        print(f"No raw data at {raw_path}. Run `make download-data` and `make validate-data` first.", file=sys.stderr)
        return 1

    df = pd.read_parquet(raw_path)
    cleaned = clean(df)
    cleaned.attrs["source"] = "PARQUET_LOCAL"
    cleaned.attrs["is_synthetic"] = False

    out_path = PROCESSED_DIR / f"{args.instrument}_{args.timeframe}.parquet"
    cleaned.to_parquet(out_path)
    print(f"Prepared {len(cleaned)}/{len(df)} bars -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
