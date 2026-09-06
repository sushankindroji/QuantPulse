import pandas as pd
from fastapi import HTTPException

from app.api import routes


def test_dataset_range_endpoint_uses_actual_rows(monkeypatch):
    df = pd.DataFrame(
        {"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2, 3]},
        index=pd.date_range("2026-09-01", periods=3, freq="h", tz="UTC"),
    )
    record = {
        "instrument": "USD_CHF",
        "source_timeframe": "1h",
        "n_rows": 3,
        "is_synthetic": False,
    }
    monkeypatch.setattr(routes.dataset_registry, "get_dataset", lambda _: record)
    monkeypatch.setattr(routes.dataset_registry, "load_dataset_dataframe", lambda _: df)
    result = routes.dataset_range(
        "ds_test",
        start="2026-09-01T01:00:00.000Z",
        end="2026-09-01T01:59:59.999Z",
    )
    assert result["bars_selected"] == 1
    assert result["selected_start"].startswith("2026-09-01T01:00:00")
    assert result["selected_end"].startswith("2026-09-01T01:00:00")


def test_research_run_file_resolution_error_is_controlled(monkeypatch):
    def fail(_cfg, log=True):
        raise FileNotFoundError("registered dataset file is unavailable for storage key 'ds_test.parquet'.")

    monkeypatch.setattr(routes, "run_full_research", fail)
    req = routes.ResearchRunRequest(
        dataset_id="ds_test",
        data_mode="uploaded",
        timeframe="1h",
    )
    try:
        routes.research_run(req)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "registered dataset file is unavailable" in str(exc.detail)
        assert "No such file or directory" not in str(exc.detail)
    else:
        raise AssertionError("Expected unavailable registered dataset to be rejected")
