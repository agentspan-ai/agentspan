/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.secrets;

import java.util.Map;

import javax.sql.DataSource;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * One-shot migration from the deprecated {@code credentials_store} table to
 * {@code secrets_store}.
 *
 * <p>Runs after the schema is applied (which creates {@code secrets_store}),
 * detects whether the legacy {@code credentials_store} still exists, copies any
 * rows it has into {@code secrets_store} (idempotent — no overwrite), and drops
 * the legacy table.</p>
 *
 * <p>SQLite doesn't have portable conditional DDL, and Postgres {@code DO} blocks
 * are awkward to ship in a {@code spring.sql.init} script, so we do the
 * existence check + copy + drop in Java.</p>
 */
@Component
public class SecretSchemaMigrator {

    private static final Logger log = LoggerFactory.getLogger(SecretSchemaMigrator.class);

    private final NamedParameterJdbcTemplate jdbc;
    private final boolean isPostgres;

    public SecretSchemaMigrator(
            @Qualifier("secretJdbc") NamedParameterJdbcTemplate jdbc, @Qualifier("secretDataSource") DataSource ds) {
        this.jdbc = jdbc;
        try (var c = ds.getConnection()) {
            this.isPostgres = c.getMetaData().getURL().startsWith("jdbc:postgresql");
        } catch (Exception e) {
            throw new IllegalStateException("could not probe credential DataSource for dialect", e);
        }
    }

    @EventListener(ApplicationReadyEvent.class)
    public void migrate() {
        if (!legacyTableExists()) return;

        // Wrap the body in try/catch — this runs during ApplicationReadyEvent
        // and an uncaught exception would crash JVM startup. In multi-replica
        // deployments (e.g. Kubernetes rolling deploy) two replicas can both
        // pass legacyTableExists() but only one wins the DROP; the other
        // replica's INSERT/DROP race would historically crash startup.
        // Logging-and-continuing is correct: migration is idempotent
        // (WHERE NOT EXISTS + DROP TABLE IF EXISTS).
        try {
            // Use a portable WHERE NOT EXISTS rather than ON CONFLICT — SQLite
            // doesn't accept `INSERT … SELECT … ON CONFLICT DO NOTHING` (it
            // requires a conflict target, and the target syntax is dialect-specific).
            // WHERE NOT EXISTS works identically on SQLite and Postgres and
            // preserves existing rows in secrets_store.
            int copied = jdbc.update(
                    "INSERT INTO secrets_store (user_id, name, encrypted_value, created_at, updated_at) "
                            + "SELECT cs.user_id, cs.name, cs.encrypted_value, cs.created_at, cs.updated_at "
                            + "FROM credentials_store cs "
                            + "WHERE NOT EXISTS ("
                            + "  SELECT 1 FROM secrets_store ss "
                            + "  WHERE ss.user_id = cs.user_id AND ss.name = cs.name)",
                    Map.of());
            // IF EXISTS so a concurrent replica that already dropped the table
            // doesn't make THIS replica throw.
            jdbc.getJdbcOperations().execute("DROP TABLE IF EXISTS credentials_store");
            log.warn(
                    "Migrated {} row(s) from legacy credentials_store → secrets_store and dropped the legacy table.",
                    copied);
        } catch (Exception e) {
            log.warn(
                    "Schema migration from credentials_store failed — server will continue with secrets_store. "
                            + "Verify legacy data manually if upgrading from a prior version. Cause: {}",
                    e.toString());
        }
    }

    private boolean legacyTableExists() {
        String sql = isPostgres
                ? "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'credentials_store'"
                : "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='credentials_store'";
        Integer n = jdbc.queryForObject(sql, Map.of(), Integer.class);
        return n != null && n > 0;
    }
}
