"""
High-level research service: ties data -> features -> regimes -> signals ->
validation -> backtest -> experiment tracking into one callable used by both
the FastAPI routes and the `make run-research` CLI, so there is exactly one
code path (no duplicated logic between API and scripts).
"""
from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from app.config import ResearchConfig
from app.data.ingestion import ResamplingError, resample_ohlcv
from app.data.providers import DataRequest, DemoProvider, get_provider
from app.domain import backtest as bt
from app.domain import validation as val
from app.domain.features import build_feature_matrix, feature_columns
from app.services.dataset_registry import get_dataset, load_dataset_dataframe
from app.services.experiment_tracker import log_experiment


def _apply_research_range(df: pd.DataFrame, range_start: str | None, range_end: str | None) -> pd.DataFrame:
    """Return a VIEW of `df` restricted to [range_start, range_end] when
    either is given. This never modifies or duplicates the underlying
    stored dataset — it's a plain pandas slice scoped to a single research
    run, exactly like `.tail()` is used for chart downsampling elsewhere.
    Out-of-range bounds are clamped to the dataset's actual availability
    rather than silently ignored or fabricated."""
    if not range_start and not range_end:
        return df
    if df.empty:
        raise ValueError("The selected dataset contains no usable rows.")
    def _utc(value: str) -> pd.Timestamp:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            return ts.tz_localize("UTC")
        return ts.tz_convert("UTC")

    try:
        start = _utc(range_start) if range_start else df.index[0]
        end = _utc(range_end) if range_end else df.index[-1]
    except (TypeError, ValueError) as exc:
        raise ValueError("Research range must use valid ISO date/time values.") from exc
    if start > end:
        raise ValueError("Research range start must be earlier than or equal to range end.")
    start = max(start, df.index[0])
    end = min(end, df.index[-1])
    selected = df.loc[start:end]
    if selected.empty:
        raise ValueError(
            f"Research range {start.isoformat()} to {end.isoformat()} contains no data in the selected dataset."
        )
    return selected


def load_data(cfg: ResearchConfig) -> pd.DataFrame:
    if cfg.dataset_id:
        record = get_dataset(cfg.dataset_id)
        if record is None:
            raise ValueError(f"Dataset '{cfg.dataset_id}' was not found. Please upload it again.")
        df = load_dataset_dataframe(cfg.dataset_id)
        source_timeframe = record["source_timeframe"]
        if source_timeframe != cfg.timeframe:
            try:
                df = resample_ohlcv(df, source_timeframe, cfg.timeframe)
            except ResamplingError as exc:
                raise ValueError(str(exc)) from exc
            df.attrs["source"] = "UPLOADED_CSV"
            df.attrs["is_synthetic"] = False
            df.attrs["instrument"] = record["instrument"]
        return _apply_research_range(df, cfg.range_start, cfg.range_end)
    if cfg.data_mode == "demo":
        provider = DemoProvider(seed=cfg.random_seed)
    else:
        provider = get_provider("parquet", cfg.instrument, cfg.data_path)
    request = DataRequest(instrument=cfg.instrument, timeframe=cfg.timeframe, n_bars=cfg.train_bars + cfg.test_bars * 6)
    return provider.fetch(request)


def run_full_research(cfg: ResearchConfig, log: bool = True) -> dict:
    df = load_data(cfg)
    effective_instrument = df.attrs.get("instrument", cfg.instrument)
    full = build_feature_matrix(df, horizons=cfg.prediction_horizons)

    leak_check = val.check_no_future_features(feature_columns(full))
    if not leak_check["ok"]:
        raise RuntimeError(f"Leakage check failed: {leak_check}")

    folds = val.walk_forward_folds(
        full.index, cfg.train_bars, cfg.test_bars, cfg.step_bars, cfg.embargo_bars
    )
    if not folds:
        raise ValueError(
            "Not enough bars for even one walk-forward fold. "
            "Reduce train_bars/test_bars or provide more data."
        )

    fold_results = []
    for fold in folds:
        leak = val.detect_leakage(fold.train_index, fold.test_index, cfg.embargo_bars)
        test_slice = full.loc[fold.test_index]
        df_slice = df.loc[fold.test_index[0] : fold.test_index[-1]]
        # Pass the raw train-period OHLCV so the regime model is fitted on
        # train data only (causal) and applied to the test slice.
        train_df_slice = df.loc[fold.train_index[0] : fold.train_index[-1]]
        result = bt.run_backtest(
            df_slice,
            test_slice,
            horizon=cfg.primary_horizon,
            exec_cfg=cfg.execution,
            risk_cfg=cfg.risk,
            train_df=train_df_slice,
        )
        fold_results.append(
            {
                "fold_id": fold.fold_id,
                "leakage_check": leak,
                "risk_report": result.risk_report,
                "signal_reports": [
                    {
                        "name": r.name,
                        "ic": asdict(r.ic),
                    }
                    for r in result.signal_reports
                ],
                "cost_sensitivity": result.cost_sensitivity.to_dict(orient="records"),
            }
        )

    metrics = {
        "n_folds": len(fold_results),
        "avg_net_sharpe": _safe_mean([f["risk_report"]["sharpe"] for f in fold_results]),
        "avg_max_drawdown": _safe_mean([f["risk_report"]["max_drawdown"] for f in fold_results]),
        "folds": fold_results,
    }

    record = None
    if log:
        record = log_experiment(
            instrument=effective_instrument,
            timeframe=cfg.timeframe,
            model="ic_weighted_signal_ensemble",
            data_mode=cfg.data_mode,
            random_seed=cfg.random_seed,
            config={
                "dataset_id": cfg.dataset_id,
                "range_start": cfg.range_start,
                "range_end": cfg.range_end,
                "prediction_horizons": cfg.prediction_horizons,
                "primary_horizon": cfg.primary_horizon,
                "train_bars": cfg.train_bars,
                "test_bars": cfg.test_bars,
                "step_bars": cfg.step_bars,
                "embargo_bars": cfg.embargo_bars,
                "execution": asdict(cfg.execution),
                "risk": asdict(cfg.risk),
            },
            metrics={"avg_net_sharpe": metrics["avg_net_sharpe"], "avg_max_drawdown": metrics["avg_max_drawdown"], "n_folds": metrics["n_folds"]},
            features=feature_columns(full),
        )

    return {
        "experiment": asdict(record) if record else None,
        "metrics": metrics,
        "data_source": df.attrs.get("source", "UNKNOWN"),
        "is_synthetic": df.attrs.get("is_synthetic", True),
        "instrument": effective_instrument,
        "timeframe": cfg.timeframe,
        "research_window": {
            "start": df.index[0].isoformat() if len(df) else None,
            "end": df.index[-1].isoformat() if len(df) else None,
            "bars_used": len(df),
            "is_full_dataset": not (cfg.range_start or cfg.range_end),
        },
    }


def _safe_mean(values: list[float]) -> float | None:
    clean = [v for v in values if v == v]  # filter NaN
    if not clean:
        return None
    return sum(clean) / len(clean)
