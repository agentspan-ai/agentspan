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
 * Unit tests for {@link CredentialSchemaMigrator}.
 *
 * <p>The migrator cleans up installations that ran an intermediate pre-release
 * build which temporarily used {@code secrets_store} as the table name.
 * Canonical name is and always was {@code credentials_store}.  These tests
 * simulate the stale-table scenario and verify the migrator copies correctly,
 * is idempotent, survives broken stale tables, and does not overwrite existing
 * rows.</p>
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
        jdbc.update("DELETE FROM credentials_store WHERE user_id = :u", Map.of("u", USER));
        jdbc.getJdbcOperations().execute("DROP TABLE IF EXISTS secrets_store");
    }

    @AfterEach
    void cleanUp() {
        jdbc.update("DELETE FROM credentials_store WHERE user_id = :u", Map.of("u", USER));
        jdbc.getJdbcOperations().execute("DROP TABLE IF EXISTS secrets_store");
    }

    @Test
    void migrate_copiesStaleRow_andDropsStaleTable() {
        // Create the stale intermediate table and seed a row.
        jdbc.getJdbcOperations()
                .execute("CREATE TABLE secrets_store ("
                        + "  user_id TEXT NOT NULL, "
                        + "  name TEXT NOT NULL, "
                        + "  encrypted_value BLOB NOT NULL, "
                        + "  created_at TEXT NOT NULL, "
                        + "  updated_at TEXT NOT NULL, "
                        + "  PRIMARY KEY (user_id, name))");

        byte[] fakeEnc = new byte[] {0x01, 0x02, 0x03, 0x04};
        jdbc.update(
                "INSERT INTO secrets_store (user_id, name, encrypted_value, created_at, updated_at) "
                        + "VALUES (:u, :n, :e, :t, :t)",
                Map.of("u", USER, "n", NAME, "e", fakeEnc, "t", "2026-05-30T00:00:00Z"));

        // Sanity: nothing yet in credentials_store for this user/name.
        Integer pre = jdbc.queryForObject(
                "SELECT COUNT(*) FROM credentials_store WHERE user_id = :u AND name = :n",
                Map.of("u", USER, "n", NAME),
                Integer.class);
        assertThat(pre).isZero();

        migrator.migrate();

        // Row landed in credentials_store.
        Integer post = jdbc.queryForObject(
                "SELECT COUNT(*) FROM credentials_store WHERE user_id = :u AND name = :n",
                Map.of("u", USER, "n", NAME),
                Integer.class);
        assertThat(post).isEqualTo(1);

        // Stale table dropped.
        Integer staleExists = jdbc.queryForObject(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='secrets_store'",
                Map.of(),
                Integer.class);
        assertThat(staleExists).isZero();
    }

    @Test
    void migrate_isIdempotent_secondCallIsNoop() {
        // No stale table present — both calls must be silent no-ops.
        migrator.migrate();
        migrator.migrate();
    }

    @Test
    void migrate_survivesBrokenStaleTable_doesNotPropagateException() {
        // Simulates a partially-created stale table (wrong schema).
        // The INSERT…SELECT will throw; migrate() must catch and log, not crash.
        jdbc.getJdbcOperations()
                .execute("CREATE TABLE secrets_store ("
                        + "  user_id TEXT NOT NULL, name TEXT NOT NULL, "
                        + "  WRONG_COLUMN BLOB NOT NULL, "
                        + "  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                        + "  PRIMARY KEY (user_id, name))");

        org.junit.jupiter.api.Assertions.assertDoesNotThrow(() -> migrator.migrate());
    }

    @Test
    void migrate_doesNotOverwriteExistingCredential() {
        // credentials_store already has a row; stale table has the same key with
        // different bytes. Migration MUST NOT clobber the existing row.
        byte[] currentValue = new byte[] {0x10, 0x11, 0x12};
        jdbc.update(
                "INSERT INTO credentials_store (user_id, name, encrypted_value, created_at, updated_at) "
                        + "VALUES (:u, :n, :e, :t, :t)",
                Map.of("u", USER, "n", NAME, "e", currentValue, "t", "2026-05-30T01:00:00Z"));

        jdbc.getJdbcOperations()
                .execute("CREATE TABLE secrets_store ("
                        + "  user_id TEXT NOT NULL, name TEXT NOT NULL, "
                        + "  encrypted_value BLOB NOT NULL, "
                        + "  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                        + "  PRIMARY KEY (user_id, name))");
        byte[] staleValue = new byte[] {(byte) 0x99, (byte) 0x88};
        jdbc.update(
                "INSERT INTO secrets_store (user_id, name, encrypted_value, created_at, updated_at) "
                        + "VALUES (:u, :n, :e, :t, :t)",
                Map.of("u", USER, "n", NAME, "e", staleValue, "t", "2026-05-30T00:00:00Z"));

        migrator.migrate();

        // The current value survives; stale value was not copied.
        byte[] actual = jdbc.queryForObject(
                "SELECT encrypted_value FROM credentials_store WHERE user_id = :u AND name = :n",
                Map.of("u", USER, "n", NAME),
                byte[].class);
        assertThat(actual).isEqualTo(currentValue);
    }
}
