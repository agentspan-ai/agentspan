/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.time.Instant;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import dev.agentspan.runtime.AgentRuntime;

/**
 * Audit gap E — schema-migration upgrade path, full pipeline.
 *
 * <p>Task A proved {@code CredentialSchemaMigrator.migrate()} copies bytes
 * correctly. This test proves those bytes are <em>actually readable</em> via
 * the public {@code GET /api/secrets/{name}} endpoint after migration —
 * which is what self-hosters care about post-upgrade.</p>
 *
 * <p>Mechanic: encrypt a value via the live store (so encryption format
 * matches the running master key), copy those encrypted bytes into a
 * synthetic {@code credentials_store} row under a different name, drop the
 * staging row from {@code credentials_store}, run the migrator, then GET via
 * the controller and assert the original plaintext comes back.</p>
 *
 * <p>Catches: a migration that copies bytes but encodes them wrong, or a
 * controller that reads from a table the migration didn't actually land in,
 * or a future encryption-format change that breaks the migrated rows.</p>
 */
@SpringBootTest(classes = AgentRuntime.class)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class SchemaMigratorUpgradePathTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private CredentialSchemaMigrator migrator;

    @Autowired
    private CredentialStoreProvider store;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String ANON = "00000000-0000-0000-0000-000000000000";
    private static final String STAGE_NAME = "_UPGRADE_TEST_STAGE";
    private static final String MIGRATED_NAME = "_UPGRADE_TEST_MIGRATED";
    private static final String PLAINTEXT = "the-secret-that-should-survive-migration";

    @BeforeEach
    void setUp() {
        store.delete(ANON, STAGE_NAME);
        store.delete(ANON, MIGRATED_NAME);
        jdbc.getJdbcOperations().execute("DROP TABLE IF EXISTS secrets_store");
    }

    @AfterEach
    void cleanUp() {
        store.delete(ANON, STAGE_NAME);
        store.delete(ANON, MIGRATED_NAME);
        jdbc.getJdbcOperations().execute("DROP TABLE IF EXISTS secrets_store");
    }

    @Test
    void migratedRow_isReadableViaPublicApi() throws Exception {
        // 1. Encrypt a plaintext through the live store (credentials_store).
        //    This guarantees the bytes are in the format the running server reads.
        store.set(ANON, STAGE_NAME, PLAINTEXT);
        byte[] encryptedBytes = jdbc.queryForObject(
                "SELECT encrypted_value FROM credentials_store WHERE user_id = :u AND name = :n",
                Map.of("u", ANON, "n", STAGE_NAME),
                byte[].class);

        // 2. Build the stale intermediate table (secrets_store) and seed a row
        //    under MIGRATED_NAME. Remove the staging row from credentials_store
        //    so MIGRATED_NAME exists only in the stale table.
        jdbc.getJdbcOperations()
                .execute("CREATE TABLE secrets_store ("
                        + "  user_id TEXT NOT NULL, "
                        + "  name TEXT NOT NULL, "
                        + "  encrypted_value BLOB NOT NULL, "
                        + "  created_at TEXT NOT NULL, "
                        + "  updated_at TEXT NOT NULL, "
                        + "  PRIMARY KEY (user_id, name))");
        jdbc.update(
                "INSERT INTO secrets_store (user_id, name, encrypted_value, created_at, updated_at) "
                        + "VALUES (:u, :n, :e, :t, :t)",
                Map.of(
                        "u",
                        ANON,
                        "n",
                        MIGRATED_NAME,
                        "e",
                        encryptedBytes,
                        "t",
                        Instant.now().toString()));
        store.delete(ANON, STAGE_NAME); // remove the staging row

        // Sanity: the migrated name is NOT yet visible via the public API.
        mvc.perform(get("/api/secrets/" + MIGRATED_NAME)).andExpect(status().isNotFound());

        // 3. Run the migrator. After this, the row should be in credentials_store.
        migrator.migrate();

        // 4. Public API reads the plaintext correctly — proves the full
        //    pipeline (legacy bytes → new table → controller decryption → HTTP).
        mvc.perform(get("/api/secrets/" + MIGRATED_NAME))
                .andExpect(status().isOk())
                .andExpect(content().string(PLAINTEXT));
    }
}
