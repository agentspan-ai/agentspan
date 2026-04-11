package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;

@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CredentialDataSourceConfigTest {

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate credentialJdbc;

    @Test
    void schemaIsCreated_usersTableExists() {
        // Query the table directly — if it doesn't exist the query throws,
        // which is a portable way to assert existence without relying on
        // database-specific metadata tables (sqlite_master, information_schema, etc.)
        assertThatCode(() ->
                        credentialJdbc.queryForObject("SELECT COUNT(*) FROM users", java.util.Map.of(), Integer.class))
                .doesNotThrowAnyException();
    }

    @Test
    void schemaIsCreated_allFourTablesExist() {
        for (String table : java.util.List.of("users", "api_keys", "credentials_store", "credentials_binding")) {
            assertThatCode(() -> credentialJdbc.queryForObject(
                            "SELECT COUNT(*) FROM " + table, java.util.Map.of(), Integer.class))
                    .as("table %s should exist and be queryable", table)
                    .doesNotThrowAnyException();
        }
    }

    /**
     * Confirms that busy_timeout is non-zero on credential pool connections.
     *
     * <p>The test URL uses SQLite's file: URI syntax (?mode=memory&cache=shared), which means
     * ?-parameters are SQLite URI params parsed by the SQLite engine — not JDBC connection
     * properties parsed by the xerial driver. busy_timeout is not a SQLite URI parameter, so it
     * cannot be set via the test URL.
     *
     * <p>busy_timeout is applied via two sources:
     * <ol>
     *   <li>Our credentialDataSource.connectionInitSql sets 15000ms on every new connection.
     *   <li>Conductor's SqliteConfiguration.initializeSqlite() overrides to 30000ms at startup.
     * </ol>
     * The connectionInitSql is the safety net for connections created after startup (e.g. after
     * HikariCP evicts and recreates the connection). Without it, a new connection would have
     * busy_timeout=0.
     */
    @Test
    void credentialConnection_hasBusyTimeoutConfigured() {
        Integer busyTimeout = credentialJdbc.queryForObject("PRAGMA busy_timeout", Map.of(), Integer.class);
        assertThat(busyTimeout)
                .as("busy_timeout must be > 0 to prevent immediate failure when another connection holds a write lock")
                .isGreaterThanOrEqualTo(15000);
    }
}
