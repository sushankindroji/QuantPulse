import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.data.providers import DataRequest, DemoProvider
from app.domain.features import build_feature_matrix


@pytest.fixture(scope="session")
def demo_df():
    provider = DemoProvider(seed=42)
    return provider.fetch(DataRequest(instrument="GBP_CAD", timeframe="1h", n_bars=2000))


@pytest.fixture(scope="session")
def full_features(demo_df):
    return build_feature_matrix(demo_df, horizons=(1, 5, 10, 20))
