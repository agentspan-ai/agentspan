-- schema-eval-postgres.sql
-- Agentspan eval observability tables (PostgreSQL variant).

CREATE TABLE IF NOT EXISTS eval_runs (
    id           TEXT PRIMARY KEY,
    agent_name   TEXT,
    timestamp    TEXT NOT NULL,
    total_cases  INTEGER NOT NULL DEFAULT 0,
    passed_cases INTEGER NOT NULL DEFAULT 0,
    tags         TEXT,
    created_by   TEXT,
    name         TEXT,
    strategy     TEXT,
    ran_by       TEXT,
    dataset      TEXT
);

-- migrations for existing installs
ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS strategy TEXT;
ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS ran_by TEXT;
ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS dataset TEXT;

CREATE TABLE IF NOT EXISTS eval_cases (
    id          TEXT PRIMARY KEY,
    eval_run_id TEXT NOT NULL,
    case_name   TEXT NOT NULL,
    passed      INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    agent_name  TEXT,
    model       TEXT,
    tags        TEXT,
    prompt      TEXT,
    output      TEXT
);

-- migrations for existing installs
ALTER TABLE eval_cases ADD COLUMN IF NOT EXISTS prompt TEXT;
ALTER TABLE eval_cases ADD COLUMN IF NOT EXISTS output TEXT;

CREATE TABLE IF NOT EXISTS eval_checks (
    id           TEXT PRIMARY KEY,
    eval_case_id TEXT NOT NULL,
    check_name   TEXT NOT NULL,
    passed       INTEGER NOT NULL DEFAULT 0,
    message      TEXT,
    score        DOUBLE PRECISION,
    reasoning    TEXT
);

CREATE TABLE IF NOT EXISTS eval_datasets (
    name       TEXT PRIMARY KEY,
    cases_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    pushed_by  TEXT,
    case_count INTEGER NOT NULL DEFAULT 0
);

-- migrations for existing installs
ALTER TABLE eval_datasets ADD COLUMN IF NOT EXISTS pushed_by TEXT;
ALTER TABLE eval_datasets ADD COLUMN IF NOT EXISTS case_count INTEGER NOT NULL DEFAULT 0;

-- indices for FK lookup performance
CREATE INDEX IF NOT EXISTS idx_eval_cases_run_id   ON eval_cases(eval_run_id);
CREATE INDEX IF NOT EXISTS idx_eval_checks_case_id ON eval_checks(eval_case_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_timestamp ON eval_runs(timestamp DESC);
