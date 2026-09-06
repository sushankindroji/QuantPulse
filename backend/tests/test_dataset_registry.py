import numpy as np
import pandas as pd
import sqlite3
import json
import pytest

from app.services import dataset_registry


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point the dataset registry at a throwaway SQLite file and storage dir
    per test so tests never pollute the real experiments/data folders."""
    db_path = tmp_path / "datasets.db"
    monkeypatch.setattr(dataset_registry, "DB_PATH", db_path)

    from app.data import storage as storage_mod

    storage_mod._datasets_storage = storage_mod.LocalStorage(tmp_path / "datasets")
    yield
    storage_mod._datasets_storage = None


def _sample_df(n=300, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    price = 1.3 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    return pd.DataFrame({"open": price, "high": price * 1.001, "low": price * 0.999, "close": price, "volume": 100.0}, index=idx)


def test_register_and_retrieve_dataset():
    df = _sample_df()
    record = dataset_registry.register_dataset(df, "test.csv", "GBP_CAD", "1h")
    fetched = dataset_registry.get_dataset(record.dataset_id)
    assert fetched is not None
    assert fetched["instrument"] == "GBP_CAD"
    assert fetched["n_rows"] == 300
    assert fetched["is_synthetic"] is False


def test_load_dataset_dataframe_roundtrips_data():
    df = _sample_df()
    record = dataset_registry.register_dataset(df, "test.csv", "EUR_USD", "1h")
    loaded = dataset_registry.load_dataset_dataframe(record.dataset_id)
    assert len(loaded) == len(df)
    assert loaded.attrs["is_synthetic"] is False
    assert loaded.attrs["instrument"] == "EUR_USD"


def test_list_datasets_returns_most_recent_first():
    dataset_registry.register_dataset(_sample_df(seed=1), "a.csv", "GBP_CAD", "1h")
    dataset_registry.register_dataset(_sample_df(seed=2), "b.csv", "EUR_USD", "1h")
    datasets = dataset_registry.list_datasets()
    assert len(datasets) == 2
    assert datasets[0]["original_filename"] == "b.csv"


def test_get_missing_dataset_returns_none():
    assert dataset_registry.get_dataset("ds_doesnotexist") is None


def test_content_hash_is_deterministic():
    df = _sample_df(seed=5)
    h1 = dataset_registry.content_hash(df)
    h2 = dataset_registry.content_hash(df.copy())
    assert h1 == h2


def test_content_hash_differs_for_different_data():
    h1 = dataset_registry.content_hash(_sample_df(seed=1))
    h2 = dataset_registry.content_hash(_sample_df(seed=2))
    assert h1 != h2


def test_filename_is_sanitized_on_registration():
    df = _sample_df()
    record = dataset_registry.register_dataset(df, "../../etc/passwd.csv", "GBP_CAD", "1h")
    assert ".." not in record.original_filename
    assert "/" not in record.original_filename


def test_registered_dataset_is_marked_unavailable_when_backing_file_is_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "datasets.db"
    monkeypatch.setattr(dataset_registry, "DB_PATH", db_path)
    from app.data import storage as storage_mod
    storage_mod._datasets_storage = storage_mod.LocalStorage(tmp_path / "datasets")
    conn = sqlite3.connect(db_path)
    conn.execute(dataset_registry.SCHEMA)
    conn.execute(
        "INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("ds_missing", "USDCHF60.csv", "USD_CHF", "1h", "ds_missing.parquet",
         "hash", 10, "2024-01-01T00:00:00+00:00", "2024-01-01T09:00:00+00:00",
         json.dumps(["open","high","low","close","volume"]), "UTC", 0, "2024-01-02T00:00:00+00:00"),
    )
    conn.commit(); conn.close()
    record = dataset_registry.get_dataset("ds_missing")
    assert record["available"] is False
    with pytest.raises(FileNotFoundError, match="registered dataset file is unavailable"):
        dataset_registry.load_dataset_dataframe("ds_missing")
    storage_mod._datasets_storage = None
