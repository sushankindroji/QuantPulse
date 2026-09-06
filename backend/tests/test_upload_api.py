import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _csv_bytes(n=800, freq="min", seed=0, ts_col="timestamp"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq=freq)
    price = 1.3 * np.exp(np.cumsum(rng.normal(0, 0.0003, n)))
    df = pd.DataFrame(
        {
            ts_col: idx,
            "open": price,
            "high": price * (1 + np.abs(rng.normal(0, 0.0005, n))),
            "low": price * (1 - np.abs(rng.normal(0, 0.0005, n))),
            "close": price * (1 + rng.normal(0, 0.0002, n)),
            "volume": rng.integers(100, 1000, n),
        }
    )
    return df.to_csv(index=False).encode()


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    """Isolate every upload test's SQLite DB and Parquet storage so tests
    don't pollute (or depend on) real project data."""
    from app.data import storage as storage_mod
    from app.services import dataset_registry as registry_mod

    monkeypatch.setattr(registry_mod, "DB_PATH", tmp_path / "datasets.db")
    storage_mod._datasets_storage = storage_mod.LocalStorage(tmp_path / "datasets")
    yield
    storage_mod._datasets_storage = None


def test_upload_valid_dukascopy_style_csv():
    csv_bytes = _csv_bytes(n=800, freq="min", ts_col="Gmt time")
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("GBPCAD_Candlestick_1_M_BID.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["instrument"] == "GBP_CAD"
    assert body["source_timeframe"] == "1min"
    assert body["rows"] > 0
    assert "dataset_id" in body


def test_upload_missing_column_returns_human_readable_422():
    df = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=300, freq="h"), "open": 1.1, "high": 1.2, "low": 1.0})
    resp = client.post("/api/datasets/upload", files={"file": ("bad.csv", df.to_csv(index=False).encode(), "text/csv")})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "Close" in detail["message"] or any("Close" in i["message"] for i in detail["issues"])


def test_upload_without_instrument_hint_asks_for_it():
    csv_bytes = _csv_bytes(n=800, freq="h")
    resp = client.post("/api/datasets/upload", files={"file": ("random_export.csv", csv_bytes, "text/csv")})
    assert resp.status_code == 422
    assert resp.json()["detail"]["needs_instrument"] is True


def test_upload_with_explicit_instrument_succeeds():
    csv_bytes = _csv_bytes(n=800, freq="h")
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("random_export.csv", csv_bytes, "text/csv")},
        data={"instrument": "usd/jpy"},
    )
    assert resp.status_code == 200
    assert resp.json()["instrument"] == "USD_JPY"


def test_upload_malformed_csv_returns_clean_error_not_traceback():
    resp = client.post("/api/datasets/upload", files={"file": ("junk.csv", b"\x00\x01\x02garbage", "text/csv")})
    assert resp.status_code == 400
    assert "Traceback" not in resp.json()["detail"]


def test_upload_empty_file_returns_clean_error():
    resp = client.post("/api/datasets/upload", files={"file": ("empty.csv", b"", "text/csv")})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_datasets_list_and_detail_endpoints():
    csv_bytes = _csv_bytes(n=800, freq="h")
    upload = client.post(
        "/api/datasets/upload",
        files={"file": ("EURUSD_1H.csv", csv_bytes, "text/csv")},
    )
    ds_id = upload.json()["dataset_id"]

    listed = client.get("/api/datasets")
    assert listed.status_code == 200
    assert any(d["dataset_id"] == ds_id for d in listed.json()["datasets"])

    detail = client.get(f"/api/datasets/{ds_id}")
    assert detail.status_code == 200
    assert detail.json()["instrument"] == "EUR_USD"

    missing = client.get("/api/datasets/ds_does_not_exist")
    assert missing.status_code == 404


def test_full_pipeline_upload_then_research_same_timeframe():
    csv_bytes = _csv_bytes(n=1500, freq="min", ts_col="Gmt time")
    upload = client.post(
        "/api/datasets/upload",
        files={"file": ("GBPUSD_Candlestick_1_M_BID.csv", csv_bytes, "text/csv")},
    )
    ds_id = upload.json()["dataset_id"]

    research = client.post(
        "/api/research/run",
        json={"dataset_id": ds_id, "timeframe": "1min", "train_bars": 800, "test_bars": 200, "step_bars": 200, "embargo_bars": 5},
    )
    assert research.status_code == 200
    body = research.json()
    assert body["instrument"] == "GBP_USD"
    assert body["is_synthetic"] is False
    assert body["data_source"] == "UPLOADED_CSV"
    assert body["metrics"]["n_folds"] > 0
    assert body["experiment"]["experiment_id"]


def test_full_pipeline_upload_then_research_with_resampling():
    csv_bytes = _csv_bytes(n=20000, freq="min", ts_col="Gmt time")
    upload = client.post(
        "/api/datasets/upload",
        files={"file": ("AUDUSD_Candlestick_1_M_BID.csv", csv_bytes, "text/csv")},
    )
    ds_id = upload.json()["dataset_id"]
    assert upload.json()["source_timeframe"] == "1min"

    research = client.post(
        "/api/research/run",
        json={"dataset_id": ds_id, "timeframe": "1h", "train_bars": 150, "test_bars": 30, "step_bars": 30, "embargo_bars": 2},
    )
    assert research.status_code == 200
    body = research.json()
    assert body["instrument"] == "AUD_USD"
    assert body["timeframe"] == "1h"


def test_upsample_request_via_api_fails_with_clear_message():
    csv_bytes = _csv_bytes(n=800, freq="h")
    upload = client.post(
        "/api/datasets/upload",
        files={"file": ("USDCAD_Candlestick_1_H_BID.csv", csv_bytes, "text/csv")},
    )
    ds_id = upload.json()["dataset_id"]

    research = client.post(
        "/api/research/run",
        json={"dataset_id": ds_id, "timeframe": "1min", "train_bars": 50, "test_bars": 10, "step_bars": 10, "embargo_bars": 1},
    )
    assert research.status_code == 400
    assert "never fabricates data" in research.json()["detail"]


def test_two_different_fx_pairs_both_work_through_same_pipeline():
    for filename, expected_instrument in [
        ("EURGBP_Candlestick_1_H_BID.csv", "EUR_GBP"),
        ("USDCAD_Candlestick_1_H_BID.csv", "USD_CAD"),
    ]:
        csv_bytes = _csv_bytes(n=800, freq="h", seed=hash(filename) % 1000)
        upload = client.post("/api/datasets/upload", files={"file": (filename, csv_bytes, "text/csv")})
        assert upload.status_code == 200
        ds_id = upload.json()["dataset_id"]

        research = client.post(
            "/api/research/run",
            json={"dataset_id": ds_id, "timeframe": "1h", "train_bars": 400, "test_bars": 100, "step_bars": 100, "embargo_bars": 5},
        )
        assert research.status_code == 200
        assert research.json()["instrument"] == expected_instrument


def test_demo_mode_still_works_unaffected_by_upload_feature():
    resp = client.post(
        "/api/research/run",
        json={"train_bars": 500, "test_bars": 100, "step_bars": 100, "embargo_bars": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["is_synthetic"] is True
    assert resp.json()["data_source"] == "DEMO_SYNTHETIC"
