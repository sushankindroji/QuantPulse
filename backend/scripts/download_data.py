#!/usr/bin/env python3
"""
`make download-data` entrypoint.

Estimates storage requirements BEFORE downloading anything, then attempts
the real download via DukascopyProvider. Per project rules, if the real
download path is unavailable in this environment, this script fails
loudly with exact manual instructions -- it does NOT fall back to
generating fake data and calling it real.
"""
from __future__ import annotations

import argparse
import sys

from app.config import RAW_DIR
from app.data.providers import DataRequest, DukascopyProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Download real historical FX data (zero-cost sources only).")
    parser.add_argument("--instrument", default="GBP_CAD")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--n-bars", type=int, default=20000)
    args = parser.parse_args()

    provider = DukascopyProvider()
    request = DataRequest(instrument=args.instrument, timeframe=args.timeframe, n_bars=args.n_bars)

    estimate = provider.estimate_storage_bytes(request)
    print(f"Estimated storage for {args.n_bars} bars of {args.instrument} @ {args.timeframe}: "
          f"~{estimate / 1024:.1f} KB")

    try:
        df = provider.fetch(request)
    except Exception as exc:
        print(f"\nReal data download failed: {exc}\n", file=sys.stderr)
        print("See docs/DATA_ACQUISITION.md for the manual import path "
              "(download from Dukascopy manually, convert to Parquet, and place "
              "it under data/raw/).", file=sys.stderr)
        print("You can continue development immediately with: make run-research "
              "(uses demo/synthetic data by default).", file=sys.stderr)
        return 1

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{args.instrument}_{args.timeframe}.parquet"
    df.to_parquet(out_path)
    print(f"Saved {len(df)} bars to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
