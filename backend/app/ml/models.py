"""
Progressive research ladder.

    naive -> linear/logistic -> random forest -> gradient boosting -> (xgboost/lightgbm if installed)

Every model implements the same tiny interface (fit/predict) so the
research harness can compare them apples-to-apples against simple
statistical baselines, per spec section 17: ML must not be the centerpiece,
and if a simpler model wins, that must be reported honestly.
"""
from __future__ import annotations

import abc

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression


class ResearchModel(abc.ABC):
    name: str

    @abc.abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ResearchModel":
        ...

    @abc.abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        ...


class NaiveBaseline(ResearchModel):
    """Predicts the historical mean forward return -- the floor every other
    model must beat to be worth its complexity."""

    name = "naive_mean_baseline"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "NaiveBaseline":
        self.mean_ = float(y.mean())
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self.mean_)


class LinearBaseline(ResearchModel):
    name = "linear_regression"

    def __init__(self):
        self.model = LinearRegression()

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return self.model.predict(X)


class RandomForestModel(ResearchModel):
    name = "random_forest"

    def __init__(self, n_estimators: int = 200, max_depth: int = 4, seed: int = 42):
        self.model = RandomForestRegressor(
            n_estimators=n_estimators, max_depth=max_depth, random_state=seed, n_jobs=-1
        )

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return self.model.predict(X)


class GradientBoostingModel(ResearchModel):
    name = "gradient_boosting"

    def __init__(self, n_estimators: int = 200, max_depth: int = 3, seed: int = 42):
        self.model = GradientBoostingRegressor(
            n_estimators=n_estimators, max_depth=max_depth, random_state=seed
        )

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return self.model.predict(X)


def try_import_xgboost() -> type[ResearchModel] | None:
    try:
        import xgboost as xgb
    except ImportError:
        return None

    class XGBoostModel(ResearchModel):
        name = "xgboost"

        def __init__(self, seed: int = 42):
            self.model = xgb.XGBRegressor(
                n_estimators=300, max_depth=4, learning_rate=0.05, random_state=seed, verbosity=0
            )

        def fit(self, X, y):
            self.model.fit(X, y)
            return self

        def predict(self, X):
            return self.model.predict(X)

    return XGBoostModel


RESEARCH_LADDER: list[type[ResearchModel]] = [
    NaiveBaseline,
    LinearBaseline,
    RandomForestModel,
    GradientBoostingModel,
]

_xgb_cls = try_import_xgboost()
if _xgb_cls is not None:
    RESEARCH_LADDER.append(_xgb_cls)
