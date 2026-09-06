"""
Alpha evaluation: Information Coefficient, IC stability, IC-by-regime,
alpha decay across horizons, and statistical significance testing.

This module makes the explicit distinction the spec requires:
    "predictive" (statistically significant IC)
        vs
    "tradable" (survives costs; see execution.py / backtest.py)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class ICResult:
    ic: float
    p_value: float
    n_obs: int
    significant_at_5pct: bool


def information_coefficient(score: pd.Series, forward_return: pd.Series) -> ICResult:
    aligned = pd.concat([score, forward_return], axis=1).dropna()
    if len(aligned) < 30:
        return ICResult(ic=np.nan, p_value=np.nan, n_obs=len(aligned), significant_at_5pct=False)
    ic, p = stats.spearmanr(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return ICResult(ic=float(ic), p_value=float(p), n_obs=len(aligned), significant_at_5pct=bool(p < 0.05))


def rolling_ic_series(score: pd.Series, forward_return: pd.Series, window: int = 250) -> pd.Series:
    aligned = pd.concat([score, forward_return], axis=1).dropna()
    aligned.columns = ["score", "fwd"]
    out = pd.Series(index=aligned.index, dtype=float)
    s = aligned["score"].values
    f = aligned["fwd"].values
    for i in range(window, len(aligned) + 1):
        seg_s = s[i - window : i]
        seg_f = f[i - window : i]
        if np.std(seg_s) == 0 or np.std(seg_f) == 0:
            out.iloc[i - 1] = np.nan
        else:
            out.iloc[i - 1] = stats.spearmanr(seg_s, seg_f)[0]
    return out


def ic_by_regime(score: pd.Series, forward_return: pd.Series, regime_labels: pd.Series) -> pd.DataFrame:
    df = pd.concat([score.rename("score"), forward_return.rename("fwd"), regime_labels.rename("regime")], axis=1).dropna()
    rows = []
    for regime, grp in df.groupby("regime"):
        res = information_coefficient(grp["score"], grp["fwd"])
        rows.append({"regime": regime, "ic": res.ic, "p_value": res.p_value, "n_obs": res.n_obs})
    return pd.DataFrame(rows).sort_values("regime")


def alpha_decay(score: pd.Series, features_with_targets: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    rows = []
    for h in horizons:
        col = f"future_return_{h}"
        if col not in features_with_targets.columns:
            continue
        res = information_coefficient(score, features_with_targets[col])
        rows.append({"horizon": h, "ic": res.ic, "p_value": res.p_value, "n_obs": res.n_obs})
    return pd.DataFrame(rows)


def bootstrap_ci(values: np.ndarray, n_boot: int = 2000, ci: float = 0.95, seed: int = 42) -> tuple[float, float, float]:
    """Return (mean, lower, upper) bootstrap CI for the mean of `values`."""
    rng = np.random.default_rng(seed)
    values = np.asarray(values)
    values = values[~np.isnan(values)]
    if len(values) == 0:
        return (np.nan, np.nan, np.nan)
    boots = rng.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
    lo = np.percentile(boots, (1 - ci) / 2 * 100)
    hi = np.percentile(boots, (1 + ci) / 2 * 100)
    return (float(values.mean()), float(lo), float(hi))


def sharpe_significance(returns: pd.Series, periods_per_year: int = 252) -> dict:
    """t-test of whether mean return is significantly different from zero,
    plus an approximate Sharpe standard error (Lo, 2002 style simplification)."""
    r = returns.dropna().values
    n = len(r)
    if n < 10:
        return {"sharpe": np.nan, "t_stat": np.nan, "p_value": np.nan, "n": n}
    mean, std = r.mean(), r.std(ddof=1)
    sharpe = mean / std * np.sqrt(periods_per_year) if std > 0 else np.nan
    t_stat, p_value = stats.ttest_1samp(r, 0.0)
    return {"sharpe": float(sharpe), "t_stat": float(t_stat), "p_value": float(p_value), "n": n}


def multiple_testing_correction(p_values: list[float], method: str = "bonferroni") -> list[float]:
    p = np.array(p_values, dtype=float)
    m = np.sum(~np.isnan(p))
    if method == "bonferroni":
        return list(np.minimum(p * m, 1.0))
    raise ValueError(f"Unknown correction method: {method}")
