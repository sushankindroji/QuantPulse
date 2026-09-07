from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field


def _sanitize(obj):
    """Recursively replace NaN/Inf with None so responses are valid JSON."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj

from app.config import ExecutionAssumptions, ResearchConfig, RiskLimits
from app.data.ingestion import ingest_csv
from app.data.providers import DataRequest, DemoProvider
from app.domain import regimes as rg
from app.domain.features import build_feature_matrix
from app.services import dataset_registry
from app.services.experiment_tracker import delete_experiment, get_experiment, list_experiments
from app.services.research_service import run_full_research

router = APIRouter()


class ResearchRunRequest(BaseModel):
    instrument: str = "GBP_CAD"
    timeframe: str = "1h"
    data_mode: str = "demo"
    dataset_id: Optional[str] = None
    primary_horizon: int = Field(default=5, ge=1, le=10_000)
    train_bars: int = Field(default=1500, ge=50, le=5_000_000)
    test_bars: int = Field(default=300, ge=10, le=5_000_000)
    step_bars: int = Field(default=300, ge=1, le=5_000_000)
    embargo_bars: int = Field(default=10, ge=0, le=5_000_000)
    random_seed: int = Field(default=42)
    spread_pips: float = Field(default=1.2, ge=0, le=10_000)
    slippage_pips: float = Field(default=0.3, ge=0, le=10_000)
    range_start: Optional[str] = None
    range_end: Optional[str] = None


@router.post("/datasets/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    instrument: Optional[str] = Form(None),
):
    """
    Accepts a CSV upload, auto-detects columns/timestamp format/timeframe,
    validates it with human-readable messages, converts it to Parquet
    internally, and registers it for research. The caller never has to
    touch the filesystem or run a CLI script.
    
    Optimized for fast response - validation and storage happen synchronously
    but are streamlined to minimize processing time.
    """
    raw_bytes = await file.read()
    
    # Quick size check before processing
    if len(raw_bytes) > 200 * 1024 * 1024:  # 200 MB
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(raw_bytes) / 1024 / 1024:.1f} MB). Maximum is 200 MB."
        )
    
    try:
        result = ingest_csv(raw_bytes, file.filename or "upload.csv")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not result.validation.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Your CSV could not be validated.",
                "issues": result.validation.as_dicts(),
                "detected_columns": result.column_map.mapping,
            },
        )

    final_instrument = instrument or result.inferred_instrument
    if not final_instrument:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "QuantPulse could not determine the currency pair from the file name. "
                           "Please specify the instrument (e.g. GBP_CAD) and upload again.",
                "issues": [],
                "needs_instrument": True,
            },
        )
    final_instrument = final_instrument.upper().replace("/", "_").replace("-", "_")

    # Register dataset (writes Parquet and inserts DB record)
    # This is the main processing step but is necessary for data integrity
    record = dataset_registry.register_dataset(
        df=result.dataframe,
        original_filename=file.filename or "upload.csv",
        instrument=final_instrument,
        source_timeframe=result.source_timeframe,
        is_synthetic=False,
    )

    # Data confidence report
    n_uploaded = result.raw_row_count
    n_usable = record.n_rows
    warnings = result.validation.as_dicts()
    errors = [w for w in warnings if w.get("severity") == "error"]
    has_warnings = len([w for w in warnings if w.get("severity") == "warning"]) > 0
    
    # Determine confidence status
    if errors:
        confidence_status = "DATA_REJECTED"
    elif n_usable < n_uploaded * 0.95 and n_uploaded - n_usable > 100:
        confidence_status = "DATA_NEEDS_REVIEW"
    elif has_warnings or n_usable < n_uploaded:
        confidence_status = "DATA_READY_WITH_CLEANING"
    else:
        confidence_status = "DATA_READY"

    return _sanitize({
        "dataset_id": record.dataset_id,
        "instrument": record.instrument,
        "source_timeframe": record.source_timeframe,
        "rows": record.n_rows,
        "start_time": record.start_time,
        "end_time": record.end_time,
        "columns": record.columns,
        "timezone": record.timezone,
        "content_hash": record.content_hash,
        "warnings": warnings,
        "data_confidence": {
            "status": confidence_status,
            "uploaded_rows": n_uploaded,
            "usable_rows": n_usable,
            "removed_rows": max(0, n_uploaded - n_usable),
            "detected_instrument": result.inferred_instrument,
            "detected_timeframe": result.source_timeframe,
            "data_source": result.data_source,
            "data_kind": result.data_kind,
            "parsed_rows": result.accounting.parsed_rows,
            "source_valid_rows": result.accounting.source_valid_rows,
            "removal_reasons": result.accounting.removal_reasons,
        },
    })


@router.get("/datasets")
def datasets(limit: int = Query(default=100, ge=1, le=1000)):
    return _sanitize({"datasets": dataset_registry.list_datasets(limit=limit)})


@router.get("/datasets/{dataset_id}")
def dataset_detail(dataset_id: str):
    record = dataset_registry.get_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _sanitize(record)


@router.get("/datasets/{dataset_id}/range")
def dataset_range(
    dataset_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Return the actual dataset coverage and the rows in the requested window."""
    record = dataset_registry.get_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = dataset_registry.load_dataset_dataframe(dataset_id)
        available_start, available_end = df.index[0], df.index[-1]
        selected = df
        requested_out_of_range = False
        if start:
            selected_start = pd.Timestamp(start)
            if selected_start.tzinfo is None:
                selected_start = selected_start.tz_localize("UTC")
            else:
                selected_start = selected_start.tz_convert("UTC")
            requested_out_of_range |= selected_start < available_start
            selected = selected.loc[selected_start:]
        if end:
            selected_end = pd.Timestamp(end)
            if selected_end.tzinfo is None:
                selected_end = selected_end.tz_localize("UTC")
            else:
                selected_end = selected_end.tz_convert("UTC")
            requested_out_of_range |= selected_end > available_end
            selected = selected.loc[:selected_end]
        if start and end:
            a = pd.Timestamp(start)
            b = pd.Timestamp(end)
            if a.tzinfo is None: a = a.tz_localize("UTC")
            else: a = a.tz_convert("UTC")
            if b.tzinfo is None: b = b.tz_localize("UTC")
            else: b = b.tz_convert("UTC")
            if a > b:
                raise ValueError("Research range start must be earlier than or equal to range end.")
        selected_start = selected.index[0] if len(selected) else None
        selected_end = selected.index[-1] if len(selected) else None
        # Mirror the backend feature warm-up safety margin used by the
        # frontend auto-configurator; the final fold validator remains the
        # source of truth.
        minimum_required_bars = 80 + 30 + 1 + 40
        return _sanitize({
            "dataset_id": dataset_id,
            "instrument": record["instrument"],
            "source_timeframe": record["source_timeframe"],
            "available_start": available_start.isoformat(),
            "available_end": available_end.isoformat(),
            "selected_start": selected_start.isoformat() if selected_start is not None else None,
            "selected_end": selected_end.isoformat() if selected_end is not None else None,
            "bars_selected": int(len(selected)),
            "bars_available": int(len(df)),
            "requested_out_of_range": requested_out_of_range,
            "sufficient_for_research": len(selected) >= minimum_required_bars,
            "minimum_required_bars": minimum_required_bars,
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/datasets/{dataset_id}/candles")
def dataset_candles(
    dataset_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
):
    """Return a bounded tail of an actual registered dataset for previews."""
    record = dataset_registry.get_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = dataset_registry.load_dataset_dataframe(dataset_id).tail(limit).reset_index()
        df["timestamp"] = df["timestamp"].astype(str)
        return _sanitize({
            "dataset_id": dataset_id,
            "instrument": record["instrument"],
            "source_timeframe": record["source_timeframe"],
            "is_synthetic": record["is_synthetic"],
            "source": "DEMO_SYNTHETIC" if record["is_synthetic"] else "UPLOADED_CSV",
            "total_rows": int(record["n_rows"]),
            "points_returned": len(df),
            "bars": df.to_dict(orient="records"),
        })
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/instruments")
def instruments():
    return {
        "primary": "GBP_CAD",
        "secondary": ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "EUR_GBP"],
    }


@router.get("/market/demo")
def market_demo(
    instrument: str = "GBP_CAD",
    timeframe: str = "1h",
    n_bars: int = Query(default=500, ge=1, le=1_000_000),
):
    provider = DemoProvider()
    df = provider.fetch(DataRequest(instrument=instrument, timeframe=timeframe, n_bars=n_bars))
    tail = df.tail(200).reset_index()
    tail["timestamp"] = tail["timestamp"].astype(str)
    return _sanitize({
        "source": df.attrs["source"],
        "is_synthetic": df.attrs["is_synthetic"],
        "bars": tail.to_dict(orient="records"),
    })


@router.get("/regimes")
def regimes(
    instrument: str = "GBP_CAD",
    timeframe: str = "1h",
    n_bars: int = Query(default=1500, ge=50, le=1_000_000),
):
    provider = DemoProvider()
    df = provider.fetch(DataRequest(instrument=instrument, timeframe=timeframe, n_bars=n_bars))
    result = rg.detect_regimes(df)
    latest = result.probabilities.iloc[-1].to_dict()
    return _sanitize({
        "method": result.method,
        "current_regime": result.labels.iloc[-1],
        "current_probabilities": latest,
        "source": df.attrs["source"],
    })


@router.post("/research/run")
def research_run(req: ResearchRunRequest):
    cfg = ResearchConfig(
        instrument=req.instrument,
        timeframe=req.timeframe,
        data_mode="uploaded" if req.dataset_id else req.data_mode,
        dataset_id=req.dataset_id,
        primary_horizon=req.primary_horizon,
        train_bars=req.train_bars,
        test_bars=req.test_bars,
        step_bars=req.step_bars,
        embargo_bars=req.embargo_bars,
        random_seed=req.random_seed,
        range_start=req.range_start,
        range_end=req.range_end,
        execution=ExecutionAssumptions(spread_pips=req.spread_pips, slippage_pips=req.slippage_pips),
        risk=RiskLimits(),
    )
    try:
        result = run_full_research(cfg, log=True)
    except Exception as exc:  # surface a clean error to the frontend
        raise HTTPException(status_code=400, detail=str(exc))
    return _sanitize(result)


@router.get("/experiments")
def experiments(limit: int = 50):
    return _sanitize({"experiments": list_experiments(limit=limit)})


@router.get("/experiments/{experiment_id}")
def experiment_detail(experiment_id: str):
    exp = get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return _sanitize(exp)


@router.delete("/experiments/{experiment_id}")
def delete_exp(experiment_id: str):
    success = delete_experiment(experiment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"status": "deleted", "experiment_id": experiment_id}
