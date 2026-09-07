"""
Modular feature engine.

Every function takes an OHLCV dataframe and returns ONLY new columns
computed from information available at or before time t (no look-ahead).
`build_feature_matrix` assembles the full feature set and drops the warm-up
rows produced by rolling windows.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def price_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    close = df["close"]
    log_close = np.log(close)
    out["log_return_1"] = log_close.diff(1)
    for w in (5, 10, 20, 50):
        out[f"return_{w}"] = close.pct_change(w)
        out[f"momentum_{w}"] = log_close.diff(w)
    roll_mean_20 = close.rolling(20).mean()
    roll_std_20 = close.rolling(20).std()
    out["zscore_20"] = (close - roll_mean_20) / roll_std_20.replace(0, np.nan)
    roll_mean_50 = close.rolling(50).mean()
    roll_std_50 = close.rolling(50).std()
    out["zscore_50"] = (close - roll_mean_50) / roll_std_50.replace(0, np.nan)
    out["dist_from_ma_20"] = (close - roll_mean_20) / roll_mean_20
    return out


def volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    log_ret = np.log(df["close"]).diff()
    for w in (10, 20, 50):
        out[f"realized_vol_{w}"] = log_ret.rolling(w).std() * np.sqrt(w)
    out["ewma_vol_10"] = log_ret.ewm(span=10).std()
    out["ewma_vol_30"] = log_ret.ewm(span=30).std()
    out["vol_ratio_10_50"] = out["realized_vol_10"] / out["realized_vol_50"].replace(0, np.nan)
    out["vol_change_10"] = out["realized_vol_10"].diff(5)
    # Parkinson range-based volatility (uses only high/low within the bar, no look-ahead)
    hl = np.log(df["high"] / df["low"]).replace([np.inf, -np.inf], np.nan)
    out["parkinson_vol_20"] = (hl ** 2).rolling(20).mean().pipe(np.sqrt) / (2 * np.sqrt(np.log(2)))
    return out


def volume_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    vol = df["volume"]
    out["volume_change_5"] = vol.pct_change(5)
    out["volume_zscore_20"] = (vol - vol.rolling(20).mean()) / vol.rolling(20).std().replace(0, np.nan)
    ret = df["close"].pct_change()
    out["volume_norm_return"] = ret / (vol.rolling(20).mean().replace(0, np.nan))
    out["activity_intensity_10"] = vol.rolling(10).mean() / vol.rolling(50).mean().replace(0, np.nan)
    return out


def microstructure_proxy_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Proxy microstructure features derivable from OHLC alone (no real book).
    These are clearly weaker than true LOB features and are documented as
    such -- see docs/MICROSTRUCTURE.md. Real order-book research lives in
    the separate FI-2010-based track (see app/domain/microstructure.py).
    """
    out = pd.DataFrame(index=df.index)
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    out["close_loc_in_range"] = (df["close"] - df["low"]) / rng
    out["bar_range_pct"] = rng / df["close"]
    out["range_zscore_20"] = (rng - rng.rolling(20).mean()) / rng.rolling(20).std().replace(0, np.nan)
    return out


def time_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    idx = df.index
    hour = idx.hour
    dow = idx.dayofweek
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    # crude session flags (UTC): London 07-16, NY 12-21, Tokyo 00-09
    out["session_london"] = ((hour >= 7) & (hour < 16)).astype(int)
    out["session_ny"] = ((hour >= 12) & (hour < 21)).astype(int)
    out["session_tokyo"] = ((hour >= 0) & (hour < 9)).astype(int)
    return out


def build_targets(df: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    """Future return / direction targets. These use FUTURE data by
    construction -- callers must never use these as features."""
    out = pd.DataFrame(index=df.index)
    log_close = np.log(df["close"])
    for h in horizons:
        fwd = log_close.shift(-h) - log_close
        out[f"future_return_{h}"] = fwd
        out[f"future_direction_{h}"] = np.sign(fwd)
    return out


FEATURE_BUILDERS = [
    price_features,
    volatility_features,
    volume_features,
    microstructure_proxy_features,
    time_features,
]


def build_feature_matrix(
    df: pd.DataFrame,
    horizons: tuple[int, ...] = (1, 5, 10, 20),
    dropna: bool = True,
) -> pd.DataFrame:
    """Assemble full feature + target matrix. Drops warm-up / tail NaNs.
    
    When dropna=True, only drops rows where ALL features are NaN (completely
    invalid rows) or where targets are NaN (can't evaluate). This preserves
    more data for signal evaluation while still ensuring each row has some
    valid features and a valid target for IC calculation.
    """
    pieces = [builder(df) for builder in FEATURE_BUILDERS]
    features = pd.concat(pieces, axis=1)
    targets = build_targets(df, horizons)
    full = pd.concat([features, targets], axis=1)
    
    if dropna:
        # Drop rows where:
        # 1. ALL feature columns are NaN (completely unusable row)
        # 2. ANY target column is NaN (can't evaluate forward returns)
        # This is much less aggressive than full dropna() and preserves data
        # where some features are valid even if others are still warming up.
        feature_cols = [c for c in full.columns if not c.startswith("future_")]
        target_cols = [c for c in full.columns if c.startswith("future_")]
        
        # Keep rows that have at least SOME valid features AND valid targets
        has_any_feature = full[feature_cols].notna().any(axis=1)
        has_all_targets = full[target_cols].notna().all(axis=1)
        full = full[has_any_feature & has_all_targets]
    
    return full


def feature_columns(full: pd.DataFrame) -> list[str]:
    return [c for c in full.columns if not c.startswith("future_")]


def target_column(horizon: int, kind: str = "return") -> str:
    return f"future_{kind}_{horizon}"
