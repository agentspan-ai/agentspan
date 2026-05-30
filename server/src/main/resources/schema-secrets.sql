-- schema-secrets.sql
-- AgentSpan secrets tables. Created with spring.sql.init.mode=always
-- using a separate DataSource bean (see SecretDataSourceConfig).
-- SQLite-compatible DDL — IF NOT EXISTS guards make this idempotent.
--
-- Migration from the older credentials_store table is handled in Java
-- (SecretSchemaMigrator) since SQLite has no portable conditional DDL.

-- Drop deprecated credentials_binding table (removed in favor of direct name
-- lookup for Conductor-parity secrets API). Safe to re-run.
DROP TABLE IF EXISTS credentials_binding;

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,          -- UUID as string
    name          TEXT NOT NULL,
    email         TEXT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT,                      -- bcrypt; NULL for API-key-only users
    created_at    TEXT NOT NULL              -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS api_keys (
    id           TEXT PRIMARY KEY,           -- UUID as string
    user_id      TEXT NOT NULL,
    key_hash     TEXT NOT NULL UNIQUE,       -- SHA-256 hex of raw key
    label        TEXT,
    last_used_at TEXT,                       -- ISO-8601 UTC, updated on use
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS secrets_store (
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    encrypted_value BLOB NOT NULL,           -- AES-256-GCM ciphertext
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (user_id, name)
);

CREATE TABLE IF NOT EXISTS secret_tags (
    user_id   TEXT NOT NULL,
    name      TEXT NOT NULL,                -- secret this tag belongs to
    tag_key   TEXT NOT NULL,
    tag_value TEXT NOT NULL,
    PRIMARY KEY (user_id, name, tag_key, tag_value)
);

-- Per-execution record of which secret names were resolved for a worker.
-- Used by SecretOutputMasker to redact secret values from execution-read responses.
CREATE TABLE IF NOT EXISTS secret_disclosures (
    execution_id TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    name         TEXT NOT NULL,              -- secret name (matches secrets_store.name)
    disclosed_at TEXT NOT NULL,              -- ISO-8601 UTC, first disclosure for this exec+name
    PRIMARY KEY (execution_id, name)
);

CREATE INDEX IF NOT EXISTS idx_secret_disclosures_user ON secret_disclosures(user_id, execution_id);
