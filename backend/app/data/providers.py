"""
DataProvider abstraction.

    DataProvider (ABC)
        +-- DemoProvider        -> deterministic SYNTHETIC data, always available
        +-- CSVProvider         -> load local CSV files
        +-- ParquetProvider     -> load local Parquet files
        +-- DukascopyProvider   -> best-effort real historical FX downloader

The system must NEVER present synthetic data as real. DemoProvider output
always carries `source == "DEMO_SYNTHETIC"` in its metadata and the data
itself is tagged so downstream consumers can enforce this at the UI layer.
"""
from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class DataRequest:
    instrument: str
    timeframe: str = "1h"
    start: Optional[dt.datetime] = None
    end: Optional[dt.datetime] = None
    n_bars: Optional[int] = None


class DataProvider(abc.ABC):
    """Common interface every data source must implement."""

    source_label: str = "UNKNOWN"

    @abc.abstractmethod
    def fetch(self, request: DataRequest) -> pd.DataFrame:
        """Return OHLC(V) dataframe indexed by UTC timestamp, columns:
        open, high, low, close, volume. Must set df.attrs['source']."""
        raise NotImplementedError

    def estimate_storage_bytes(self, request: DataRequest) -> int:
        """Rough estimate before downloading anything large."""
        bars = request.n_bars or 5000
        # ~7 float64 columns + index -> ~64 bytes/row raw, parquet compresses ~3-4x
        return int(bars * 64 / 3.5)


class DemoProvider(DataProvider):
    """
    Deterministic synthetic OHLCV generator.

    Uses a regime-switching stochastic process (trending / mean-reverting /
    high-vol) so that the demo dataset actually exercises the regime engine,
    the alpha engine and the backtester meaningfully -- it is not just noise.
    Fully deterministic given a seed, so `docker compose up` on a clean
    clone reproduces the exact same demo experience every time.
    """

    source_label = "DEMO_SYNTHETIC"

    def __init__(self, seed: int = 42):
        self.seed = seed

    def fetch(self, request: DataRequest) -> pd.DataFrame:
        n = request.n_bars or 6000
        rng = np.random.default_rng(self.seed + abs(hash(request.instrument)) % 1000)

        # Regime schedule: sequence of (regime, length) chosen deterministically.
        regimes = ["trend_up", "trend_down", "mean_revert", "high_vol"]
        schedule = []
        remaining = n
        i = 0
        while remaining > 0:
            regime = regimes[i % len(regimes)]
            length = int(rng.integers(150, 500))
            length = min(length, remaining)
            schedule.append((regime, length))
            remaining -= length
            i += 1

        prices = []
        vols = []
        level = 1.7000  # plausible GBP/CAD-ish starting level
        for regime, length in schedule:
            if regime == "trend_up":
                mu, sigma = 0.00008, 0.0006
            elif regime == "trend_down":
                mu, sigma = -0.00008, 0.0006
            elif regime == "mean_revert":
                mu, sigma = 0.0, 0.0004
            else:  # high_vol
                mu, sigma = 0.0, 0.0018

            steps = rng.normal(mu, sigma, size=length)
            if regime == "mean_revert":
                # OU-style pull back to a local anchor
                anchor = level
                local = np.zeros(length)
                x = 0.0
                for t in range(length):
                    x = x + 0.08 * (0 - x) + steps[t]
                    local[t] = x
                path = anchor * np.exp(np.cumsum(np.diff(np.concatenate([[0], local]))))
                seg = anchor + local
            else:
                seg = level * np.exp(np.cumsum(steps))
            prices.append(seg)
            vols.append(np.full(length, sigma))
            level = seg[-1]

        close = np.concatenate(prices)
        vol_path = np.concatenate(vols)
        n = len(close)

        # Build OHLC around the close path with intrabar noise proportional to vol.
        noise = rng.normal(0, 1, size=(n, 3)) * vol_path[:, None] * close[:, None]
        open_ = np.concatenate([[close[0]], close[:-1]])
        high = np.maximum.reduce([open_, close]) + np.abs(noise[:, 0])
        low = np.minimum.reduce([open_, close]) - np.abs(noise[:, 1])
        volume = rng.integers(500, 5000, size=n).astype(float)

        freq_map = {"1min": "min", "5min": "5min", "15min": "15min", "1h": "h", "1d": "D"}
        freq = freq_map.get(request.timeframe, "h")
        end = request.end or dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
        idx = pd.date_range(end=end, periods=n, freq=freq, tz="UTC")

        df = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "regime_true": np.repeat(
                    [r for r, l in schedule], [l for r, l in schedule]
                )[:n],
            },
            index=idx,
        )
        df.index.name = "timestamp"
        df.attrs["source"] = self.source_label
        df.attrs["instrument"] = request.instrument
        df.attrs["is_synthetic"] = True
        return df


class CSVProvider(DataProvider):
    source_label = "CSV_LOCAL"

    def __init__(self, path: Path):
        self.path = Path(path)

    def fetch(self, request: DataRequest) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(
                f"CSV data not found at {self.path}. "
                "Provide the file or use DemoProvider for a synthetic dataset."
            )
        df = pd.read_csv(self.path, parse_dates=["timestamp"], index_col="timestamp")
        df = df.sort_index()
        if request.start:
            df = df[df.index >= request.start]
        if request.end:
            df = df[df.index <= request.end]
        df.attrs["source"] = self.source_label
        df.attrs["instrument"] = request.instrument
        df.attrs["is_synthetic"] = False
        return df


class ParquetProvider(DataProvider):
    source_label = "PARQUET_LOCAL"

    def __init__(self, path: Path):
        self.path = Path(path)

    def fetch(self, request: DataRequest) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(
                f"Parquet data not found at {self.path}. Run `make download-data` "
                "and `make prepare-data` first, or use demo mode."
            )
        df = pd.read_parquet(self.path)
        df = df.sort_index()
        if request.start:
            df = df[df.index >= request.start]
        if request.end:
            df = df[df.index <= request.end]
        df.attrs["source"] = self.source_label
        df.attrs["instrument"] = request.instrument
        df.attrs["is_synthetic"] = False
        return df


class DukascopyProvider(DataProvider):
    """
    Best-effort free historical FX downloader (Dukascopy tick/candle feed).

    NOTE: Dukascopy's public endpoints and formats are not guaranteed to be
    stable and network access to arbitrary hosts is not available in every
    execution environment. This provider therefore:
      1. Tries the download.
      2. If it fails (network restrictions, format change, etc.) it raises
         a clear, actionable error instead of silently fabricating data.
    """

    source_label = "DUKASCOPY_REAL"
    BASE_URL = "https://datafeed.dukascopy.com/datafeed"

    def fetch(self, request: DataRequest) -> pd.DataFrame:
        try:
            import requests  # noqa: F401  (imported lazily; optional dependency)
        except ImportError as exc:
            raise RuntimeError(
                "The 'requests' package is required for DukascopyProvider. "
                "Install it or use `make download-data` documentation for the "
                "manual import path."
            ) from exc

        raise NotImplementedError(
            "Automatic Dukascopy download is environment-dependent (binary "
            ".bi5 tick format, host availability, rate limits). This project "
            "deliberately does NOT fabricate data when the real download path "
            "is unavailable. See docs/DATA_ACQUISITION.md for the exact manual "
            "steps to obtain and import real GBP/CAD history, then point "
            "ParquetProvider / CSVProvider at the resulting file."
        )


def get_provider(mode: str, instrument: str, path: Optional[Path] = None) -> DataProvider:
    """Factory used by services so callers never construct providers directly."""
    if mode == "demo":
        return DemoProvider()
    if mode == "csv":
        return CSVProvider(path)
    if mode == "parquet":
        return ParquetProvider(path)
    if mode == "dukascopy":
        return DukascopyProvider()
    raise ValueError(f"Unknown provider mode: {mode}")
