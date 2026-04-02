package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

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
        assertThatCode(() -> credentialJdbc.queryForObject(
                "SELECT COUNT(*) FROM users",
                java.util.Map.of(),
                Integer.class))
                .doesNotThrowAnyException();
    }

    @Test
    void schemaIsCreated_allFourTablesExist() {
        for (String table : java.util.List.of("users", "api_keys", "credentials_store", "credentials_binding")) {
            assertThatCode(() -> credentialJdbc.queryForObject(
                    "SELECT COUNT(*) FROM " + table,
                    java.util.Map.of(),
                    Integer.class))
                    .as("table %s should exist and be queryable", table)
                    .doesNotThrowAnyException();
        }
    }
}
