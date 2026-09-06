#!/usr/bin/env python3
"""
`make run-research` entrypoint.

Calls the exact same `run_full_research` service used by the FastAPI route,
so there is one code path for research regardless of whether it's invoked
from the CLI or the web UI.
"""
from __future__ import annotations

import argparse
import json

from app.config import ExecutionAssumptions, EXPERIMENTS_DIR, ResearchConfig, RiskLimits
from app.services.research_service import run_full_research


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full QuantPulse walk-forward research pipeline.")
    parser.add_argument("--instrument", default="GBP_CAD")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--data-mode", default="demo", choices=["demo", "real"])
    parser.add_argument("--train-bars", type=int, default=1500)
    parser.add_argument("--test-bars", type=int, default=300)
    parser.add_argument("--step-bars", type=int, default=300)
    parser.add_argument("--embargo-bars", type=int, default=10)
    parser.add_argument("--primary-horizon", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    cfg = ResearchConfig(
        instrument=args.instrument,
        timeframe=args.timeframe,
        data_mode=args.data_mode,
        train_bars=args.train_bars,
        test_bars=args.test_bars,
        step_bars=args.step_bars,
        embargo_bars=args.embargo_bars,
        primary_horizon=args.primary_horizon,
        random_seed=args.seed,
        execution=ExecutionAssumptions(),
        risk=RiskLimits(),
    )

    result = run_full_research(cfg, log=True)

    print(f"\nData source: {result['data_source']} (synthetic={result['is_synthetic']})")
    print(f"Experiment ID: {result['experiment']['experiment_id'] if result['experiment'] else 'not logged'}")
    print(f"Folds: {result['metrics']['n_folds']}")
    print(f"Avg net Sharpe (out-of-sample, cost-adjusted): {result['metrics']['avg_net_sharpe']}")
    print(f"Avg max drawdown: {result['metrics']['avg_max_drawdown']}")

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = EXPERIMENTS_DIR / "last_run_summary.json"
    with open(summary_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nFull results written to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
