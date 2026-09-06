"""
Regime-detection layer.

Default methodology: Gaussian HMM over (returns, realized volatility) when
`hmmlearn` is available, with a statistically-defensible fallback
(Gaussian Mixture Model on the same features) so the platform still works
in environments where hmmlearn cannot be installed. The method used is
always recorded in the output so results are reproducible/auditable.

Regime labels are NOT hard-coded a priori: we fit K components and then
label each component post-hoc from its fitted mean return / volatility,
so "trending" vs "mean-reverting" vs "high-vol" is a statistical
description of what the model actually found, not an assumption.

CAUSAL USAGE (walk-forward research):
    Use fit_regimes(train_df) → FittedRegimeModel
    then apply_regimes(fitted_model, test_df) → RegimeResult
    so regime classification of test bars only uses information the
    model could have had at the time (i.e. train-period statistics).

    detect_regimes() remains available for exploratory / dashboard use
    where no train/test split is needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

try:
    from hmmlearn.hmm import GaussianHMM

    HMM_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    HMM_AVAILABLE = False


@dataclass
class RegimeResult:
    method: str
    n_regimes: int
    labels: pd.Series          # hard label per timestamp
    probabilities: pd.DataFrame  # soft probabilities, one column per regime
    regime_names: dict[int, str]
    causal: bool = False       # True when fitted on train data, applied to test data


@dataclass
class FittedRegimeModel:
    """A trained regime model that can be applied to unseen (test) data.
    Carries everything needed to label new bars without re-fitting."""
    model: Any                 # fitted GaussianHMM or GaussianMixture
    method: str                # "hmm" | "gmm_fallback"
    n_regimes: int
    regime_names: dict[int, str]


def _regime_inputs(df: pd.DataFrame) -> pd.DataFrame:
    log_ret = np.log(df["close"]).diff()
    vol = log_ret.rolling(20).std()
    trend = log_ret.rolling(20).mean()
    x = pd.DataFrame({"return": log_ret, "vol": vol, "trend": trend}).dropna()
    return x


def _name_components(means: np.ndarray) -> dict[int, str]:
    """Label components post-hoc from fitted (return, vol, trend) means."""
    names = {}
    vol_col = means[:, 1]
    trend_col = means[:, 2]
    high_vol_idx = int(np.argmax(vol_col))
    for i in range(means.shape[0]):
        if i == high_vol_idx and vol_col[i] > np.median(vol_col) * 1.3:
            names[i] = "high_vol"
        elif trend_col[i] > 1e-5:
            names[i] = "trend_up"
        elif trend_col[i] < -1e-5:
            names[i] = "trend_down"
        else:
            names[i] = "mean_revert"
    return names


def _build_prob_df(
    probs: np.ndarray,
    labels: np.ndarray,
    index: pd.Index,
    names: dict[int, str],
    n_regimes: int,
) -> tuple[pd.DataFrame, pd.Series]:
    """Shared helper: build probability DataFrame and label Series from raw
    model output, deduplicating column names when two components share the
    same post-hoc label (e.g. two mean-revert regimes)."""
    prob_df = pd.DataFrame(probs, index=index, columns=[names[i] for i in range(n_regimes)])
    if prob_df.columns.duplicated().any():
        cols: list[str] = []
        seen: dict[str, int] = {}
        for c in prob_df.columns:
            seen[c] = seen.get(c, 0) + 1
            cols.append(c if seen[c] == 1 else f"{c}_{seen[c]}")
        prob_df.columns = cols
    label_series = pd.Series(labels, index=index, name="regime").map(names)
    return prob_df, label_series


def fit_regimes(
    train_df: pd.DataFrame,
    n_regimes: int = 4,
    method: str = "auto",
    seed: int = 42,
) -> FittedRegimeModel:
    """Fit a regime model on `train_df` and return the fitted model object
    without applying it to any data.  Call `apply_regimes()` to label a
    separate (e.g. test) slice causally.

    This separates fit from predict so walk-forward backtests never let the
    regime classifier see future test-period data during fitting."""
    x = _regime_inputs(train_df)
    X = x.values

    use_hmm = HMM_AVAILABLE and method in ("auto", "hmm")
    fitted_model: Any = None
    used_method = "gmm_fallback"

    if use_hmm:
        try:
            m = GaussianHMM(
                n_components=n_regimes,
                covariance_type="diag",
                n_iter=200,
                random_state=seed,
            )
            m.fit(X)
            fitted_model = m
            used_method = "hmm"
        except Exception:
            use_hmm = False

    if not use_hmm:
        m = GaussianMixture(
            n_components=n_regimes, covariance_type="diag", random_state=seed
        )
        m.fit(X)
        fitted_model = m
        used_method = "gmm_fallback"

    means = fitted_model.means_
    names = _name_components(means)
    return FittedRegimeModel(
        model=fitted_model,
        method=used_method,
        n_regimes=n_regimes,
        regime_names=names,
    )


def apply_regimes(
    fitted: FittedRegimeModel,
    test_df: pd.DataFrame,
) -> RegimeResult:
    """Apply a pre-fitted regime model to `test_df`.  No fitting happens
    here — the component means and covariances are fixed from the training
    data, so no future information leaks into the regime labels."""
    x = _regime_inputs(test_df)
    if len(x) == 0:
        # Not enough data for rolling features; return empty result.
        empty = pd.Series(dtype=str, name="regime")
        empty_probs = pd.DataFrame()
        return RegimeResult(
            method=fitted.method,
            n_regimes=fitted.n_regimes,
            labels=empty,
            probabilities=empty_probs,
            regime_names=fitted.regime_names,
            causal=True,
        )

    X = x.values
    probs = fitted.model.predict_proba(X)
    if fitted.method == "hmm":
        labels = fitted.model.predict(X)
    else:
        labels = fitted.model.predict(X)

    prob_df, label_series = _build_prob_df(
        probs, labels, x.index, fitted.regime_names, fitted.n_regimes
    )
    return RegimeResult(
        method=fitted.method,
        n_regimes=fitted.n_regimes,
        labels=label_series,
        probabilities=prob_df,
        regime_names=fitted.regime_names,
        causal=True,
    )


def detect_regimes(
    df: pd.DataFrame, n_regimes: int = 4, method: str = "auto", seed: int = 42
) -> RegimeResult:
    """Fit and apply a regime model on a single slice of data.

    This is appropriate for exploratory analysis and dashboard display where
    there is no train/test split.  For walk-forward backtests, use the
    causal fit_regimes() + apply_regimes() API instead."""
    x = _regime_inputs(df)
    X = x.values

    use_hmm = HMM_AVAILABLE and method in ("auto", "hmm")
    if use_hmm:
        try:
            model = GaussianHMM(
                n_components=n_regimes,
                covariance_type="diag",
                n_iter=200,
                random_state=seed,
            )
            model.fit(X)
            probs = model.predict_proba(X)
            labels = model.predict(X)
            means = model.means_
            used_method = "hmm"
        except Exception:
            use_hmm = False

    if not use_hmm:
        model = GaussianMixture(
            n_components=n_regimes, covariance_type="diag", random_state=seed
        )
        model.fit(X)
        probs = model.predict_proba(X)
        labels = model.predict(X)
        means = model.means_
        used_method = "gmm_fallback"

    names = _name_components(means)
    prob_df, label_series = _build_prob_df(probs, labels, x.index, names, n_regimes)

    return RegimeResult(
        method=used_method,
        n_regimes=n_regimes,
        labels=label_series,
        probabilities=prob_df,
        regime_names=names,
        causal=False,
    )
