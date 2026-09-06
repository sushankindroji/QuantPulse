from fastapi.testclient import TestClient

from app.config import ExecutionAssumptions, RiskLimits
from app.domain.backtest import run_backtest
from app.main import app


def test_run_backtest_produces_full_result(demo_df, full_features):
    sub_df = demo_df.loc[full_features.index[0] : full_features.index[-1]]
    result = run_backtest(
        sub_df,
        full_features,
        horizon=5,
        exec_cfg=ExecutionAssumptions(),
        risk_cfg=RiskLimits(),
    )
    assert len(result.signal_reports) > 0
    assert "sharpe" in result.risk_report
    assert len(result.cost_sensitivity) > 0
    assert result.regime_result is not None


def test_backtest_net_sharpe_le_gross_sharpe_under_costs(demo_df, full_features):
    sub_df = demo_df.loc[full_features.index[0] : full_features.index[-1]]
    cfg = ExecutionAssumptions(spread_pips=5.0, slippage_pips=2.0)  # stress costs
    result = run_backtest(sub_df, full_features, horizon=5, exec_cfg=cfg, risk_cfg=RiskLimits())
    assert result.net_returns.sum() <= result.gross_returns.sum() + 1e-9


client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_market_demo_endpoint_labels_synthetic():
    resp = client.get("/api/market/demo?n_bars=300")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_synthetic"] is True
    assert body["source"] == "DEMO_SYNTHETIC"
    assert len(body["bars"]) > 0


def test_research_run_endpoint_returns_json_safe_metrics():
    resp = client.post(
        "/api/research/run",
        json={"train_bars": 500, "test_bars": 100, "step_bars": 100, "embargo_bars": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metrics"]["n_folds"] > 0
    assert body["is_synthetic"] is True


def test_experiments_list_endpoint():
    resp = client.get("/api/experiments")
    assert resp.status_code == 200
    assert "experiments" in resp.json()


def test_research_request_rejects_invalid_bar_parameters():
    resp = client.post("/api/research/run", json={"train_bars": 0})
    assert resp.status_code == 422


def test_market_demo_rejects_negative_bar_count():
    resp = client.get("/api/market/demo?n_bars=-1")
    assert resp.status_code == 422


def test_research_request_accepts_and_propagates_range_fields(monkeypatch):
    from app.api import routes

    captured = {}

    def fake_run(cfg, log=True):
        captured["range_start"] = cfg.range_start
        captured["range_end"] = cfg.range_end
        return {"metrics": {"n_folds": 1}, "is_synthetic": True, "instrument": cfg.instrument, "timeframe": cfg.timeframe}

    monkeypatch.setattr(routes, "run_full_research", fake_run)
    resp = client.post(
        "/api/research/run",
        json={
            "train_bars": 100,
            "test_bars": 20,
            "step_bars": 20,
            "range_start": "2024-01-01T00:00:00Z",
            "range_end": "2024-02-01T00:00:00Z",
        },
    )
    assert resp.status_code == 200
    assert captured == {
        "range_start": "2024-01-01T00:00:00Z",
        "range_end": "2024-02-01T00:00:00Z",
    }
