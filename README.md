# QuantPulse

**Upload market data → Research it → Understand the evidence.**

QuantPulse is a quantitative research platform, not a trading bot. You
upload historical FX data (or use the built-in synthetic demo), and
QuantPulse tells you — honestly — whether there's evidence of a genuine,
short-horizon, cost-surviving trading signal in it.

---

## What it does

- Ingests any FX CSV export (Dukascopy or similar) through the website —
  no manual column renaming, no CSV to Parquet conversion, no CLI required.
- Auto-detects columns, timestamp format, instrument, and source timeframe;
  validates the data with plain-English errors, not Python tracebacks.
- Resamples to whatever research timeframe you choose (e.g. 1-minute source
  data to 1-hour research bars), and refuses -- clearly -- if you ask for a
  timeframe finer than what you uploaded, rather than inventing data.
- Runs a full research pipeline: feature engineering -> regime detection ->
  independent signal evaluation (Information Coefficient, significance) ->
  walk-forward validation with embargo -> execution-cost simulation (spread,
  slippage, latency) -> risk metrics (Sharpe, Sortino, drawdown, VaR/ES).
- Never fabricates results. If a signal isn't statistically significant, it
  gets zero weight. If a strategy loses money after costs, that's exactly
  what gets reported.
- Works for **any** FX pair discovered from your uploaded data -- GBP/CAD is
  only the default demo instrument, not a hardcoded assumption.

---

## How to start it

You need Docker Desktop installed and running. Nothing else.

```bash
git clone <this-repo>
cd quantpulse
docker compose up --build
```

Open:

```
http://localhost:3000
```

That's the whole setup. The Dashboard loads immediately using the included
synthetic demo dataset (clearly labeled **SYNTHETIC DEMO DATA -- NOT REAL
MARKET HISTORY**), so you can explore the platform before uploading
anything real.

---

## How to get historical FX data

1. Open the official [Dukascopy Historical Data Export](https://www.dukascopy.com/swiss/english/marketwatch/historical/)
   (linked directly inside the app's **New Research** page too).
2. Pick any currency pair, a date range, and export as CSV.

No conversion, no renaming -- see "How to upload" below.

---

## How to upload a CSV

1. In the app, click **New Research** in the top navigation.
2. Drag your CSV into the upload box (or click to choose a file).
3. QuantPulse validates and converts it automatically. You'll see a preview:
   instrument, source timeframe, row count, date range, detected columns,
   timezone -- plus any warnings (e.g. duplicate timestamps that were
   deduplicated).
4. If the instrument couldn't be guessed from the filename, you'll be asked
   to type it in (e.g. `GBP_CAD`) -- nothing is assumed silently.
5. Click **Continue to Research Configuration**.

If the file is invalid, you'll see a specific, human-readable reason (e.g.
*"Your CSV is missing a Close column."*) instead of a stack trace.

---

## How to run research

1. On the **Research Lab** page, your uploaded dataset is pre-selected (or
   choose the demo dataset / a previous upload).
2. Choose a **research timeframe** -- it can be coarser than your source data
   (QuantPulse resamples: open=first, high=max, low=min, close=last,
   volume=sum). Requesting something finer than your source data produces a
   clear error, not fabricated bars.
3. Set the prediction horizon, walk-forward window sizes, and cost
   assumptions (spread/slippage), or leave the sensible defaults.
4. Click **Run Research**.

---

## How to understand results

The Research Lab explains, in plain language:
- **What was tested** -- which signals, on which instrument/timeframe, over
  how many walk-forward folds.
- **Does it survive costs?** -- every Sharpe/Sortino/drawdown number shown
  is already net of spread, slippage and latency; nothing is a
  gross/inflated figure.
- **Does it survive regimes?** -- per-fold breakdown so you can see whether
  results are stable or the product of one lucky window.
- **Is it statistically significant?** -- signals with a non-significant
  Information Coefficient contribute zero weight to the combined signal.

Every run is saved to the **Experiment Registry**, with full configuration,
dataset version (content hash), and metrics, so any result is reproducible
and auditable later.

---

## How to run tests

```bash
docker compose exec backend python3 -m pytest tests/ -v
```

**100+ tests** cover data providers, CSV ingestion (column mapping,
timestamp parsing, resampling, validation), the dataset registry, storage,
feature engineering (no look-ahead), walk-forward validation, execution
costs, risk metrics, signals/evaluation, regimes, the full backtest
pipeline, and the API end-to-end (including uploading a CSV and running
research on it).

C++17 order book / execution engine tests:

```bash
cd cpp_engine && mkdir -p build && cd build && cmake .. && make -j"$(nproc)" && ./run_cpp_tests
```

---

## Environment Variables

Copy `.env.example` to `.env` to override defaults locally:

**Backend:**
- `QP_EXPERIMENTS_DB` — Path to SQLite experiments database (default: `experiments/experiments.db`)
- `QP_DATASETS_DB` — Path to SQLite datasets registry (default: `experiments/datasets.db`)
- `QP_DATA_DIR` — Data directory root (default: `data/`)
- `QP_EXPERIMENTS_DIR` — Experiments directory (default: `experiments/`)
- `DATABASE_URL` — PostgreSQL connection string (production only; SQLite used locally)
- `QP_DATA_MODE` — `demo` (synthetic) or `uploaded` (default: `demo`)
- `QP_STORAGE_BACKEND` — `local` (default; for dev) or `s3` (future: production with S3)
- `QUANTPULSE_CORS_ORIGINS` — Comma-separated list of allowed CORS origins (default: `*` for local dev; set to frontend URL in production)

**Frontend:**
- `NEXT_PUBLIC_API_URL` — Backend API URL, visible to browser (default: `http://localhost:8000`)

For production deployments, set these via your platform's environment variable configuration (Render, Vercel).

---

## How to deploy

The architecture is deployment-ready without introducing infrastructure
you don't need (no Kubernetes, Kafka, or Spark):

- **Frontend** -> Vercel (Next.js, standalone output already configured)
- **Backend** -> Render (FastAPI + Docker)
- **Database** -> managed PostgreSQL (`db/schema.sql` is the production schema)

Local development never depends on paid infrastructure -- SQLite is used
automatically when no production Postgres setup is present.

**Important for Render-style ephemeral filesystems:** uploaded dataset
storage goes through a `StorageBackend` abstraction
(`app/data/storage.py`). Local development uses `LocalStorage` against a
bind-mounted volume; production should implement an S3-compatible backend
behind the same interface before relying on persistent uploads in a
container with an ephemeral disk. See the comments in `storage.py` for
exactly what to implement.

---

## Architecture (for contributors)

```
backend/app/
  config.py          Instrument/timeframe/horizon/cost config -- nothing hard-coded
  data/
    ingestion.py        CSV -> validated, normalized, resampled OHLCV (the upload pipeline)
    storage.py           Storage abstraction (local now, S3-ready interface)
    providers.py          DemoProvider (synthetic) | CSV/Parquet/Dukascopy providers
  domain/
    features.py, regimes.py, signals.py, evaluation.py, validation.py,
    execution.py, risk.py, backtest.py    -- research engine, instrument-agnostic
  ml/models.py         Naive -> Linear -> RandomForest -> GradientBoosting -> XGBoost ladder
  services/
    dataset_registry.py    Uploaded dataset metadata + retrieval
    experiment_tracker.py   Every research run, fully reproducible
    research_service.py      Single code path used by both the API and CLI scripts
  api/routes.py        FastAPI endpoints, incl. /api/datasets/upload
cpp_engine/             C++17 limit order book + matching engine + execution simulator (pybind11)
frontend/app/
  import/               "New Research" upload page
  research/               Research Lab (dataset + config + evidence-first results)
  dashboard/, alpha/, backtest/, execution/, microstructure/, paper/, experiments/
db/schema.sql          PostgreSQL schema for production experiment/dataset metadata
docs/                   DATA_ACQUISITION.md, MICROSTRUCTURE.md
testersteps.txt          Copy-paste steps for a fresh tester to verify the whole flow
```

Developer-only CLI scripts (`make download-data/validate-data/prepare-data/run-research`)
still exist under `backend/scripts/` for scripting/automation, but the
normal user workflow is entirely through the website.

---

## Honesty guarantees baked into the code

- CSV ingestion never fabricates finer-grained data than what was uploaded
  (`ResamplingError` is raised with a clear explanation instead).
- `combine_signals()` gives zero weight to any signal that isn't
  statistically significant (p >= 0.05).
- Every dataset and every API response carries `is_synthetic` / a clear
  `source` label so demo output can never be mistaken for real results.
- Uploaded filenames are sanitized and confined to the storage root
  (path-traversal-safe); uploads are size-capped (200 MB) and only CSV is
  accepted.
- If a hypothesis fails (non-significant IC, negative net Sharpe after
  costs), the experiment record shows that plainly.

## Target roles

Quant Research / Quant Trading / Algo Trading / HFT / Quant Dev / Financial
Data Science, at firms including Jane Street, Citadel, Optiver, IMC,
Millennium, Jump Trading, DRW, Two Sigma, WorldQuant, and Indian
quant/HFT firms (AlphaGrep, Quadeye, Graviton, NK Securities, Futures First,
Estee Advisors, Qube, and others).
