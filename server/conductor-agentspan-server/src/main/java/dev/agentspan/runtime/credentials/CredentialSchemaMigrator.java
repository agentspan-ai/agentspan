/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

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
 * One-shot cleanup for installations that ran an intermediate dev build which
 * temporarily renamed the table to {@code secrets_store}.
 *
 * <p>Runs after the schema is applied (which creates {@code credentials_store}),
 * checks whether a stale {@code secrets_store} table still exists, copies any
 * rows that are not already in {@code credentials_store} (idempotent — no
 * overwrite), then drops {@code secrets_store}.</p>
 *
 * <p>This is a no-op for all released versions: the canonical table has always
 * been {@code credentials_store}. The intermediate name only appeared in
 * pre-release development builds.</p>
 */
@Component
public class CredentialSchemaMigrator {

    private static final Logger log = LoggerFactory.getLogger(CredentialSchemaMigrator.class);

    private final NamedParameterJdbcTemplate jdbc;
    private final boolean isPostgres;

    public CredentialSchemaMigrator(
            @Qualifier("credentialJdbc") NamedParameterJdbcTemplate jdbc,
            @Qualifier("credentialDataSource") DataSource ds) {
        this.jdbc = jdbc;
        try (var c = ds.getConnection()) {
            this.isPostgres = c.getMetaData().getURL().startsWith("jdbc:postgresql");
        } catch (Exception e) {
            throw new IllegalStateException("could not probe credential DataSource for dialect", e);
        }
    }

    @EventListener(ApplicationReadyEvent.class)
    public void migrate() {
        if (!staleTableExists()) return;

        // Wrap in try/catch — runs during ApplicationReadyEvent; an uncaught exception
        // would crash JVM startup. Multi-replica safe: WHERE NOT EXISTS + DROP IF EXISTS.
        try {
            int copied = jdbc.update(
                    "INSERT INTO credentials_store (user_id, name, encrypted_value, created_at, updated_at) "
                            + "SELECT s.user_id, s.name, s.encrypted_value, s.created_at, s.updated_at "
                            + "FROM secrets_store s "
                            + "WHERE NOT EXISTS ("
                            + "  SELECT 1 FROM credentials_store c "
                            + "  WHERE c.user_id = s.user_id AND c.name = s.name)",
                    Map.of());
            jdbc.getJdbcOperations().execute("DROP TABLE IF EXISTS secrets_store");
            log.warn(
                    "Migrated {} row(s) from stale secrets_store → credentials_store and dropped the stale table.",
                    copied);
        } catch (Exception e) {
            log.warn(
                    "secrets_store cleanup failed — server will continue with credentials_store. "
                            + "Verify data manually if upgrading from a pre-release build. Cause: {}",
                    e.toString());
        }
    }

    /** Returns true only if the stale intermediate table name exists. */
    private boolean staleTableExists() {
        String sql = isPostgres
                ? "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'secrets_store'"
                : "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='secrets_store'";
        Integer n = jdbc.queryForObject(sql, Map.of(), Integer.class);
        return n != null && n > 0;
    }
}
