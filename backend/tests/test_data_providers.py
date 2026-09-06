import pytest

from app.data.providers import CSVProvider, DataRequest, DemoProvider, DukascopyProvider, ParquetProvider


def test_demo_provider_deterministic():
    p1 = DemoProvider(seed=7)
    p2 = DemoProvider(seed=7)
    req = DataRequest(instrument="GBP_CAD", timeframe="1h", n_bars=500)
    df1 = p1.fetch(req)
    df2 = p2.fetch(req)
    assert (df1["close"].values == df2["close"].values).all()


def test_demo_provider_is_labeled_synthetic(demo_df):
    assert demo_df.attrs["source"] == "DEMO_SYNTHETIC"
    assert demo_df.attrs["is_synthetic"] is True


def test_demo_provider_has_required_columns(demo_df):
    for col in ("open", "high", "low", "close", "volume"):
        assert col in demo_df.columns


def test_csv_provider_missing_file_raises(tmp_path):
    provider = CSVProvider(tmp_path / "does_not_exist.csv")
    with pytest.raises(FileNotFoundError):
        provider.fetch(DataRequest(instrument="GBP_CAD"))


def test_parquet_provider_missing_file_raises(tmp_path):
    provider = ParquetProvider(tmp_path / "does_not_exist.parquet")
    with pytest.raises(FileNotFoundError):
        provider.fetch(DataRequest(instrument="GBP_CAD"))


def test_dukascopy_provider_never_fabricates_data():
    """Per spec: the app must NEVER silently generate fake data and present
    it as real. DukascopyProvider must fail loudly, not fall back silently."""
    provider = DukascopyProvider()
    with pytest.raises((NotImplementedError, RuntimeError)):
        provider.fetch(DataRequest(instrument="GBP_CAD"))
