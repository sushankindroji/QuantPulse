"""
Experiment tracking.

Uses SQLite by default (zero external dependency, works out of the box for
`docker compose up` demo mode) with a schema that maps 1:1 onto the
PostgreSQL schema in db/schema.sql for production deployments -- swapping
the engine is a connection-string change, not a rewrite (see
DATABASE_URL env var).
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import EXPERIMENTS_DIR

DB_PATH = Path(os.environ.get("QP_EXPERIMENTS_DB", str(EXPERIMENTS_DIR / "experiments.db")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    model TEXT NOT NULL,
    data_mode TEXT NOT NULL,
    random_seed INTEGER NOT NULL,
    git_commit TEXT,
    created_at TEXT NOT NULL,
    config_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    features_json TEXT NOT NULL
);
"""


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


@dataclass
class ExperimentRecord:
    experiment_id: str
    instrument: str
    timeframe: str
    model: str
    data_mode: str
    random_seed: int
    config: dict[str, Any]
    metrics: dict[str, Any]
    features: list[str]
    git_commit: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def next_experiment_id(prefix: str = "QP") -> str:
    conn = _connect()
    try:
        n = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    finally:
        conn.close()
    return f"{prefix}-{n + 1:05d}"


def log_experiment(
    instrument: str,
    timeframe: str,
    model: str,
    data_mode: str,
    random_seed: int,
    config: dict[str, Any],
    metrics: dict[str, Any],
    features: list[str],
) -> ExperimentRecord:
    record = ExperimentRecord(
        experiment_id=next_experiment_id(),
        instrument=instrument,
        timeframe=timeframe,
        model=model,
        data_mode=data_mode,
        random_seed=random_seed,
        config=config,
        metrics=metrics,
        features=features,
        git_commit=_git_commit(),
    )
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                record.experiment_id,
                record.instrument,
                record.timeframe,
                record.model,
                record.data_mode,
                record.random_seed,
                record.git_commit,
                record.created_at,
                json.dumps(config, default=str),
                json.dumps(metrics, default=str),
                json.dumps(features),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return record


def list_experiments(limit: int = 50) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT experiment_id, instrument, timeframe, model, data_mode, created_at, metrics_json "
            "FROM experiments ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        out.append(
            {
                "experiment_id": r[0],
                "instrument": r[1],
                "timeframe": r[2],
                "model": r[3],
                "data_mode": r[4],
                "created_at": r[5],
                "metrics": json.loads(r[6]),
            }
        )
    return out


def get_experiment(experiment_id: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    cols = [
        "experiment_id", "instrument", "timeframe", "model", "data_mode",
        "random_seed", "git_commit", "created_at", "config_json", "metrics_json", "features_json",
    ]
    d = dict(zip(cols, row))
    d["config"] = json.loads(d.pop("config_json"))
    d["metrics"] = json.loads(d.pop("metrics_json"))
    d["features"] = json.loads(d.pop("features_json"))
    return d


def delete_experiment(experiment_id: str) -> bool:
    """Delete an experiment by ID. Returns True if deleted, False if not found."""
    conn = _connect()
    try:
        cursor = conn.execute(
            "DELETE FROM experiments WHERE experiment_id = ?", (experiment_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
