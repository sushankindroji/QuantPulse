-- QuantPulse PostgreSQL schema for application/metadata state.
-- Analytical market/research data lives separately in DuckDB + Parquet
-- (see data/ and app/data/providers.py) -- this schema is only for
-- experiment bookkeeping and (future) paper-trading state.
--
-- The default local/demo experience uses SQLite (see
-- app/services/experiment_tracker.py) so `docker compose up` needs zero
-- setup; this file is what a production deployment would run instead.

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id     TEXT PRIMARY KEY,
    instrument        TEXT NOT NULL,
    timeframe         TEXT NOT NULL,
    model             TEXT NOT NULL,
    data_mode         TEXT NOT NULL,
    random_seed       INTEGER NOT NULL,
    git_commit        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    config            JSONB NOT NULL,
    metrics           JSONB NOT NULL,
    features          JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_parameters (
    id              SERIAL PRIMARY KEY,
    experiment_id   TEXT REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    param_name      TEXT NOT NULL,
    param_value     TEXT
);

CREATE TABLE IF NOT EXISTS experiment_metrics (
    id              SERIAL PRIMARY KEY,
    experiment_id   TEXT REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    metric_name     TEXT NOT NULL,
    metric_value    DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id      TEXT PRIMARY KEY,
    instrument      TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    source          TEXT NOT NULL,
    is_synthetic    BOOLEAN NOT NULL DEFAULT true,
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ,
    n_bars          INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research_runs (
    run_id          TEXT PRIMARY KEY,
    experiment_id   TEXT REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    dataset_id      TEXT REFERENCES datasets(dataset_id),
    fold_id         INTEGER,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS signals (
    signal_name         TEXT PRIMARY KEY,
    description         TEXT,
    expected_horizon    INTEGER,
    direction_hint      TEXT
);

CREATE TABLE IF NOT EXISTS paper_orders (
    order_id        BIGSERIAL PRIMARY KEY,
    instrument      TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity        DOUBLE PRECISION NOT NULL,
    limit_price     DOUBLE PRECISION,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_fills (
    fill_id         BIGSERIAL PRIMARY KEY,
    order_id        BIGINT REFERENCES paper_orders(order_id) ON DELETE CASCADE,
    price           DOUBLE PRECISION NOT NULL,
    quantity        DOUBLE PRECISION NOT NULL,
    filled_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_positions (
    instrument      TEXT PRIMARY KEY,
    net_quantity    DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_price       DOUBLE PRECISION,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id    TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_experiments_created_at ON experiments (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_experiment_metrics_experiment_id ON experiment_metrics (experiment_id);
