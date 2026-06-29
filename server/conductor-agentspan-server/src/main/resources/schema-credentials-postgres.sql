-- schema-credentials-postgres.sql
-- AgentSpan secrets tables for PostgreSQL.
-- Loaded by SecretDataSourceConfig when spring.datasource.url starts with jdbc:postgresql.
-- IF NOT EXISTS guards make this idempotent (safe to re-run on restart).
--
-- Differences from schema-credentials.sql (SQLite):
--   - encrypted_value uses BYTEA instead of BLOB (PostgreSQL binary type)
--   - All other column types are identical (TEXT compatibility maintained)
--
-- Migration from the older credentials_store table is handled in Java
-- (SecretSchemaMigrator) so the SQL stays portable.

DROP TABLE IF EXISTS credentials_binding;

CREATE TABLE IF NOT EXISTS credentials_store (
    user_id         TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    encrypted_value BYTEA   NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    PRIMARY KEY (user_id, name)
);

-- Tags not supported — secret_tags table is omitted.

-- credential_disclosures (per-execution disclosure tracking for output masking)
-- is an enterprise feature and not included in the OSS schema.
