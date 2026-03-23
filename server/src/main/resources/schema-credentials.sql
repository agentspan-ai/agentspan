-- schema-credentials.sql
-- Agentspan credential tables. Created with spring.sql.init.mode=always
-- using a separate DataSource bean (see CredentialDataSourceConfig).
-- SQLite-compatible DDL — IF NOT EXISTS guards make this idempotent.

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

CREATE TABLE IF NOT EXISTS credentials_store (
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    encrypted_value BLOB NOT NULL,           -- AES-256-GCM ciphertext
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (user_id, name)
);

CREATE TABLE IF NOT EXISTS credentials_binding (
    user_id     TEXT NOT NULL,
    logical_key TEXT NOT NULL,              -- what code declares: "GITHUB_TOKEN"
    store_name  TEXT NOT NULL,             -- what is stored:     "my-github-prod-key"
    PRIMARY KEY (user_id, logical_key)
);
