/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;

/**
 * Audit Gap A — {@code CredentialSchemaMigrator} integration test.
 *
 * <p>Catches: data-loss bug if the legacy-to-new migration ever breaks (typo
 * column name, wrong ON CONFLICT clause, the legacy table not actually
 * dropped, …). A bug here silently destroys self-hosters' secrets on upgrade.</p>
 *
 * <p>The migrator runs once on {@code ApplicationReadyEvent}. By the time this
 * test runs the legacy table is already gone (Spring boot has fired the event).
 * We re-create the table by hand, populate a row that matches the schema, then
 * invoke {@code migrate()} directly. Verifies copy, drop, and idempotency.</p>
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CredentialSchemaMigratorTest {

    @Autowired
    private CredentialSchemaMigrator migrator;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String USER = "schema-migrator-user-001";
    private static final String NAME = "_SCHEMA_MIGR_TEST_KEY";

    @BeforeEach
    void setUp() {
        // Make sure no rows linger from prior runs.
        jdbc.update("DELETE FROM secrets_store WHERE user_id = :u", Map.of("u", USER));
        // Ensure legacy table doesn't exist before the test sets it up.
        jdbc.getJdbcOperations().execute("DROP TABLE IF EXISTS credentials_store");
    }

    @AfterEach
    void cleanUp() {
        jdbc.update("DELETE FROM secrets_store WHERE user_id = :u", Map.of("u", USER));
        jdbc.getJdbcOperations().execute("DROP TABLE IF EXISTS credentials_store");
    }

    @Test
    void migrate_copiesLegacyRow_andDropsLegacyTable() {
        // Re-create the legacy table and seed a row.
        jdbc.getJdbcOperations()
                .execute("CREATE TABLE credentials_store ("
                        + "  user_id TEXT NOT NULL, "
                        + "  name TEXT NOT NULL, "
                        + "  encrypted_value BLOB NOT NULL, "
                        + "  created_at TEXT NOT NULL, "
                        + "  updated_at TEXT NOT NULL, "
                        + "  PRIMARY KEY (user_id, name))");

        byte[] fakeEnc = new byte[] {0x01, 0x02, 0x03, 0x04};
        jdbc.update(
                "INSERT INTO credentials_store (user_id, name, encrypted_value, created_at, updated_at) "
                        + "VALUES (:u, :n, :e, :t, :t)",
                Map.of("u", USER, "n", NAME, "e", fakeEnc, "t", "2026-05-30T00:00:00Z"));

        // Sanity: nothing yet in secrets_store for this user
        Integer pre = jdbc.queryForObject(
                "SELECT COUNT(*) FROM secrets_store WHERE user_id = :u AND name = :n",
                Map.of("u", USER, "n", NAME),
                Integer.class);
        assertThat(pre).isZero();

        // Act
        migrator.migrate();

        // Row landed in the new table
        Integer post = jdbc.queryForObject(
                "SELECT COUNT(*) FROM secrets_store WHERE user_id = :u AND name = :n",
                Map.of("u", USER, "n", NAME),
                Integer.class);
        assertThat(post).isEqualTo(1);

        // Legacy table dropped
        Integer legacyExists = jdbc.queryForObject(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='credentials_store'",
                Map.of(),
                Integer.class);
        assertThat(legacyExists).isZero();
    }

    @Test
    void migrate_isIdempotent_secondCallIsNoop() {
        // After the legacy table is already gone, a second migrate() call must
        // be a no-op (no exception, no double-copy attempt).
        migrator.migrate(); // first call (legacy table absent: no-op)
        migrator.migrate(); // second call: still no-op, must not throw
        // Surviving this method without exception is the assertion.
    }

    @Test
    void migrate_survivesBrokenLegacyTable_doesNotPropagateException() {
        // Simulates the multi-replica boot race: legacyTableExists() returns
        // true but by the time migrate() executes its INSERT/DROP, the table
        // is in an unexpected state (dropped by another replica, schema drift,
        // etc.). Pre-fix the migrator's exception propagated out, killing the
        // ApplicationReadyEvent handler and crashing JVM startup. After fix:
        // migrate() catches and logs, server continues to boot.
        //
        // We trigger the failure path deterministically by giving the legacy
        // table the wrong schema (missing required column). The INSERT…SELECT
        // throws — and the test asserts the exception does NOT escape migrate().
        jdbc.getJdbcOperations()
                .execute("CREATE TABLE credentials_store ("
                        + "  user_id TEXT NOT NULL, name TEXT NOT NULL, "
                        + "  WRONG_COLUMN BLOB NOT NULL, "
                        + "  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                        + "  PRIMARY KEY (user_id, name))");

        // Must not throw — migrate() should tolerate any SQL failure during
        // the migration step and log a warning instead of crashing startup.
        org.junit.jupiter.api.Assertions.assertDoesNotThrow(() -> migrator.migrate());
    }

    @Test
    void migrate_doesNotOverwriteExistingSecret() {
        // Existing secret with same (user_id, name) already in secrets_store.
        // Legacy table has a row with the SAME key — migration MUST NOT
        // clobber the existing one (ON CONFLICT DO NOTHING).
        byte[] currentValue = new byte[] {0x10, 0x11, 0x12};
        jdbc.update(
                "INSERT INTO secrets_store (user_id, name, encrypted_value, created_at, updated_at) "
                        + "VALUES (:u, :n, :e, :t, :t)",
                Map.of("u", USER, "n", NAME, "e", currentValue, "t", "2026-05-30T01:00:00Z"));

        jdbc.getJdbcOperations()
                .execute("CREATE TABLE credentials_store ("
                        + "  user_id TEXT NOT NULL, "
                        + "  name TEXT NOT NULL, "
                        + "  encrypted_value BLOB NOT NULL, "
                        + "  created_at TEXT NOT NULL, "
                        + "  updated_at TEXT NOT NULL, "
                        + "  PRIMARY KEY (user_id, name))");
        byte[] staleValue = new byte[] {(byte) 0x99, (byte) 0x88};
        jdbc.update(
                "INSERT INTO credentials_store (user_id, name, encrypted_value, created_at, updated_at) "
                        + "VALUES (:u, :n, :e, :t, :t)",
                Map.of("u", USER, "n", NAME, "e", staleValue, "t", "2026-05-30T00:00:00Z"));

        migrator.migrate();

        // The current value survives; the stale legacy value is NOT pulled in.
        byte[] actual = jdbc.queryForObject(
                "SELECT encrypted_value FROM secrets_store WHERE user_id = :u AND name = :n",
                Map.of("u", USER, "n", NAME),
                byte[].class);
        assertThat(actual).isEqualTo(currentValue);
    }
}
