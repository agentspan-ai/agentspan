-- schema-eval.sql
-- Agentspan eval observability tables. Created on startup via EvalSchemaConfig.
-- SQLite-compatible DDL — IF NOT EXISTS guards make this idempotent.

CREATE TABLE IF NOT EXISTS eval_runs (
    id           TEXT PRIMARY KEY,          -- UUID
    agent_name   TEXT,
    timestamp    TEXT NOT NULL,             -- ISO-8601 UTC
    total_cases  INTEGER NOT NULL DEFAULT 0,
    passed_cases INTEGER NOT NULL DEFAULT 0,
    tags         TEXT,                      -- JSON array of strings
    created_by   TEXT,
    name         TEXT,                      -- user-defined run name (e.g. "eval_handoff_v2")
    strategy     TEXT,                      -- orchestration strategy
    ran_by       TEXT                       -- script filename or "UI"
);

-- migrations: add columns for existing installs (errors silently ignored via continueOnError)
ALTER TABLE eval_runs ADD COLUMN name TEXT;
ALTER TABLE eval_runs ADD COLUMN strategy TEXT;
ALTER TABLE eval_runs ADD COLUMN ran_by TEXT;

CREATE TABLE IF NOT EXISTS eval_cases (
    id          TEXT PRIMARY KEY,           -- UUID
    eval_run_id TEXT NOT NULL,              -- FK → eval_runs.id
    case_name   TEXT NOT NULL,
    passed      INTEGER NOT NULL DEFAULT 0, -- 0=false, 1=true
    error       TEXT,
    agent_name  TEXT,
    model       TEXT,
    tags        TEXT,                       -- JSON array of strings
    prompt      TEXT,                       -- original prompt sent to agent
    output      TEXT                        -- agent response text
);

-- migrations
ALTER TABLE eval_cases ADD COLUMN prompt TEXT;
ALTER TABLE eval_cases ADD COLUMN output TEXT;

CREATE TABLE IF NOT EXISTS eval_checks (
    id           TEXT PRIMARY KEY,          -- UUID
    eval_case_id TEXT NOT NULL,             -- FK → eval_cases.id
    check_name   TEXT NOT NULL,
    passed       INTEGER NOT NULL DEFAULT 0,
    message      TEXT,
    score        REAL,                      -- semantic score 0-1; null for deterministic checks
    reasoning    TEXT                       -- LLM judge reasoning; null for deterministic checks
);

CREATE TABLE IF NOT EXISTS eval_datasets (
    name       TEXT PRIMARY KEY,            -- user-defined unique dataset name
    cases_json TEXT NOT NULL,              -- JSON array of case objects
    updated_at TEXT NOT NULL,              -- ISO-8601 UTC
    pushed_by  TEXT,                       -- username / script that pushed this dataset
    case_count INTEGER NOT NULL DEFAULT 0  -- pre-computed case count for fast list queries
);

-- migrations
ALTER TABLE eval_datasets ADD COLUMN pushed_by TEXT;
ALTER TABLE eval_datasets ADD COLUMN case_count INTEGER NOT NULL DEFAULT 0;

-- indices for FK lookup performance
CREATE INDEX IF NOT EXISTS idx_eval_cases_run_id   ON eval_cases(eval_run_id);
CREATE INDEX IF NOT EXISTS idx_eval_checks_case_id ON eval_checks(eval_case_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_timestamp ON eval_runs(timestamp DESC);
