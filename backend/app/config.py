"""
Central configuration for QuantPulse.

Everything that varies per-run (instrument, timeframe, horizon, cost
assumptions, data mode) lives here so no module hard-codes GBP/CAD or
any other instrument. GBP/CAD is simply the *default*.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

def _project_root() -> Path:
    """Locate the application root without depending on the process cwd.

    Local development runs the backend from ``backend/`` while Docker copies
    the backend into ``/app``.  Prefer an explicit root when supplied, then
    locate a real project root by looking for its data/experiments markers.
    """
    explicit = os.environ.get("QP_PROJECT_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()

    here = Path(__file__).resolve()
    candidates = [here.parents[2], here.parents[1], Path.cwd(), Path.cwd().parent]
    # A source checkout has an unmistakable frontend/ marker. Prefer it over
    # backend-local data directories that may have been created by an older
    # version of the application.
    for candidate in candidates:
        if (candidate / "frontend").is_dir():
            return candidate.resolve()
    # In Docker the backend is copied to /app and frontend is a separate
    # container, so /app/data is the canonical mounted storage.
    for candidate in candidates:
        if (candidate / "data").is_dir() and candidate.name != "backend":
            return candidate.resolve()
    return here.parents[1].resolve()


import os

REPO_ROOT = _project_root()
DATA_DIR = Path(os.environ.get("QP_DATA_DIR", str(REPO_ROOT / "data"))).expanduser().resolve()
EXPERIMENTS_DIR = Path(
    os.environ.get("QP_EXPERIMENTS_DIR", str(REPO_ROOT / "experiments"))
).expanduser().resolve()
DEMO_DIR = DATA_DIR / "demo"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

for d in (DATA_DIR, DEMO_DIR, RAW_DIR, PROCESSED_DIR, EXPERIMENTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DataMode = Literal["demo", "real", "uploaded"]


@dataclass
class ExecutionAssumptions:
    """Configurable, explicit execution-cost model. Nothing here is free."""

    spread_pips: float = 1.2          # typical GBP/CAD spread
    slippage_pips: float = 0.3
    commission_per_lot: float = 0.0   # most retail FX brokers: spread-only
    latency_bars: int = 1             # signal at bar t fills at bar t+latency
    pip_size: float = 0.0001
    max_position: float = 1.0         # in lots, abstracted to [-1, 1] exposure


@dataclass
class RiskLimits:
    target_annual_vol: float = 0.10
    max_position: float = 1.0
    max_leverage: float = 3.0
    max_drawdown_stop: float = 0.25


@dataclass
class ResearchConfig:
    instrument: str = "GBP_CAD"
    timeframe: str = "1h"                 # pandas offset alias family
    prediction_horizons: tuple = (1, 5, 10, 20)
    primary_horizon: int = 5
    data_mode: DataMode = "demo"
    dataset_id: str | None = None         # if set, research runs against an uploaded dataset
    range_start: str | None = None        # ISO date/datetime — optional research-window start
    range_end: str | None = None          # ISO date/datetime — optional research-window end
    train_bars: int = 2000
    test_bars: int = 500
    step_bars: int = 500
    embargo_bars: int = 10
    random_seed: int = 42
    execution: ExecutionAssumptions = field(default_factory=ExecutionAssumptions)
    risk: RiskLimits = field(default_factory=RiskLimits)

    @property
    def data_path(self) -> Path:
        base = DEMO_DIR if self.data_mode == "demo" else PROCESSED_DIR
        return base / f"{self.instrument}_{self.timeframe}.parquet"


DEFAULT_CONFIG = ResearchConfig()
