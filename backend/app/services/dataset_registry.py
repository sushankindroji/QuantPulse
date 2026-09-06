"""
Dataset registry.

Tracks every uploaded (or demo) dataset's metadata -- instrument, source
timeframe, row count, date range, column set, storage location, content
hash/version -- in the same lightweight SQLite store used for experiment
tracking (zero external setup for local/demo use; swappable for Postgres
in production the same way `experiment_tracker.py` is).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import EXPERIMENTS_DIR
from app.data.storage import get_datasets_storage, new_dataset_id, sanitize_filename, require_dataset_path

DB_PATH = Path(os.environ.get("QP_DATASETS_DB", str(EXPERIMENTS_DIR / "datasets.db")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    instrument TEXT NOT NULL,
    source_timeframe TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    n_rows INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    columns_json TEXT NOT NULL,
    timezone TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


@dataclass
class DatasetRecord:
    dataset_id: str
    original_filename: str
    instrument: str
    source_timeframe: str
    storage_key: str
    content_hash: str
    n_rows: int
    start_time: str
    end_time: str
    columns: list[str]
    timezone: str = "UTC"
    is_synthetic: bool = False
    uploaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def content_hash(df: pd.DataFrame) -> str:
    """Stable content hash used as the dataset "version" for experiment
    tracking / reproducibility, independent of the original filename."""
    payload = pd.util.hash_pandas_object(df, index=True).values.tobytes()
    return hashlib.sha256(payload).hexdigest()[:16]


def register_dataset(
    df: pd.DataFrame,
    original_filename: str,
    instrument: str,
    source_timeframe: str,
    is_synthetic: bool = False,
) -> DatasetRecord:
    dataset_id = new_dataset_id()
    storage_key = f"{dataset_id}.parquet"
    storage = get_datasets_storage()

    # Write to a local temp path then persist through the storage
    # abstraction, so a future S3 backend only needs its own save_bytes/read.
    tmp_path = storage.path_for(storage_key)
    df.to_parquet(tmp_path)

    record = DatasetRecord(
        dataset_id=dataset_id,
        original_filename=sanitize_filename(original_filename),
        instrument=instrument,
        source_timeframe=source_timeframe,
        storage_key=storage_key,
        content_hash=content_hash(df),
        n_rows=len(df),
        start_time=str(df.index.min()),
        end_time=str(df.index.max()),
        columns=list(df.columns),
        is_synthetic=is_synthetic,
    )

    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record.dataset_id,
                record.original_filename,
                record.instrument,
                record.source_timeframe,
                record.storage_key,
                record.content_hash,
                record.n_rows,
                record.start_time,
                record.end_time,
                json.dumps(record.columns),
                record.timezone,
                int(record.is_synthetic),
                record.uploaded_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return record


_COLUMNS = [
    "dataset_id", "original_filename", "instrument", "source_timeframe", "storage_key",
    "content_hash", "n_rows", "start_time", "end_time", "columns_json", "timezone",
    "is_synthetic", "uploaded_at",
]


def _row_to_dict(row: tuple) -> dict[str, Any]:
    d = dict(zip(_COLUMNS, row))
    d["columns"] = json.loads(d.pop("columns_json"))
    d["is_synthetic"] = bool(d["is_synthetic"])
    return d


def _with_availability(record: dict[str, Any]) -> dict[str, Any]:
    """Expose truthful runtime availability without leaking filesystem paths."""
    try:
        path = require_dataset_path(record["storage_key"])
        record["available"] = True
        record["availability_error"] = None
        record["storage_size_bytes"] = path.stat().st_size
    except (OSError, ValueError) as exc:
        record["available"] = False
        record["availability_error"] = str(exc)
        record["storage_size_bytes"] = 0
    return record


def list_datasets(limit: int = 100) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM datasets ORDER BY uploaded_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [_with_availability(_row_to_dict(r)) for r in rows]


def get_dataset(dataset_id: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
    finally:
        conn.close()
    return _with_availability(_row_to_dict(row)) if row else None


def load_dataset_dataframe(dataset_id: str) -> pd.DataFrame:
    record = get_dataset(dataset_id)
    if record is None:
        raise KeyError(f"No dataset found with id {dataset_id}")
    path = require_dataset_path(record["storage_key"])
    try:
        df = pd.read_parquet(path)
    except (OSError, ValueError, ImportError) as exc:
        raise RuntimeError(
            f"Dataset '{dataset_id}' is registered but could not be read from "
            "its canonical storage file. Re-import the dataset if the file is "
            "corrupt or unavailable."
        ) from exc
    if df.empty:
        raise ValueError(f"Dataset '{dataset_id}' contains no readable rows.")
    required = {"open", "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(
            f"Dataset '{dataset_id}' is not a valid OHLC dataset; missing columns: "
            f"{', '.join(sorted(missing))}."
        )
    if len(df) != int(record["n_rows"]):
        raise ValueError(
            f"Dataset '{dataset_id}' does not match its registry metadata "
            f"(registered {record['n_rows']} rows, file contains {len(df)})."
        )
    actual_hash = content_hash(df)
    if actual_hash != record["content_hash"]:
        raise ValueError(
            f"Dataset '{dataset_id}' does not match its registered content version. "
            "Re-import the dataset to restore a consistent registry entry."
        )
    df = df.sort_index()
    df.attrs["source"] = "UPLOADED_CSV" if not record["is_synthetic"] else "DEMO_SYNTHETIC"
    df.attrs["is_synthetic"] = record["is_synthetic"]
    df.attrs["instrument"] = record["instrument"]
    return df
