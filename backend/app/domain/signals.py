"""
Alpha / signal framework.

Each AlphaSignal is independently evaluable: it maps a feature matrix to a
[-1, 1] directional score, WITHOUT peeking at targets, and declares its
metadata (expected horizon, required features, regime compatibility) so the
evaluation layer can score it in isolation before anything gets combined.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class SignalMeta:
    name: str
    description: str
    required_features: list[str]
    expected_horizon: int
    direction_hint: str  # "momentum" | "reversion" | "vol" | "microstructure"


class AlphaSignal(abc.ABC):
    meta: SignalMeta

    @abc.abstractmethod
    def score(self, features: pd.DataFrame) -> pd.Series:
        """Return a signed score per row, using only that row's features."""
        raise NotImplementedError

    def check_available(self, features: pd.DataFrame) -> bool:
        return all(c in features.columns for c in self.meta.required_features)


def _zscore_clip(s: pd.Series, clip: float = 3.0) -> pd.Series:
    z = (s - s.mean()) / (s.std() + 1e-12)
    return z.clip(-clip, clip) / clip


class MomentumSignal(AlphaSignal):
    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.meta = SignalMeta(
            name=f"momentum_{lookback}",
            description=f"Sign/strength of {lookback}-bar log-return momentum.",
            required_features=[f"momentum_{lookback}"],
            expected_horizon=lookback // 2 or 1,
            direction_hint="momentum",
        )

    def score(self, features: pd.DataFrame) -> pd.Series:
        return _zscore_clip(features[self.meta.required_features[0]])


class MeanReversionSignal(AlphaSignal):
    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        col = f"zscore_{lookback}"
        self.meta = SignalMeta(
            name=f"mean_reversion_{lookback}",
            description=f"Negative of {lookback}-bar price z-score (fade extremes).",
            required_features=[col],
            expected_horizon=max(lookback // 4, 1),
            direction_hint="reversion",
        )

    def score(self, features: pd.DataFrame) -> pd.Series:
        col = self.meta.required_features[0]
        return -_zscore_clip(features[col])


class VolatilitySignal(AlphaSignal):
    """Volatility-regime-conditioned momentum: scale momentum down in
    high vol-ratio periods (a common, testable microstructure-adjacent idea)."""

    def __init__(self, mom_lookback: int = 10):
        self.mom_lookback = mom_lookback
        self.meta = SignalMeta(
            name=f"vol_adjusted_momentum_{mom_lookback}",
            description="Momentum scaled inversely by short/long volatility ratio.",
            required_features=[f"momentum_{mom_lookback}", "vol_ratio_10_50"],
            expected_horizon=mom_lookback,
            direction_hint="vol",
        )

    def score(self, features: pd.DataFrame) -> pd.Series:
        mom, vr = self.meta.required_features
        raw = features[mom] / (features[vr].replace(0, np.nan).abs() + 1e-6)
        return _zscore_clip(raw.fillna(0))


class MicrostructureProxySignal(AlphaSignal):
    """Uses OHLC-derived proxy microstructure features (close-location-in-range)."""

    def __init__(self):
        self.meta = SignalMeta(
            name="microstructure_proxy",
            description="Close-location-in-range as a proxy for buy/sell pressure.",
            required_features=["close_loc_in_range"],
            expected_horizon=1,
            direction_hint="microstructure",
        )

    def score(self, features: pd.DataFrame) -> pd.Series:
        col = self.meta.required_features[0]
        centered = features[col] - 0.5
        return _zscore_clip(centered)


DEFAULT_SIGNALS: list[AlphaSignal] = [
    MomentumSignal(5),
    MomentumSignal(20),
    MomentumSignal(50),
    MeanReversionSignal(20),
    MeanReversionSignal(50),
    VolatilitySignal(10),
    MicrostructureProxySignal(),
]
