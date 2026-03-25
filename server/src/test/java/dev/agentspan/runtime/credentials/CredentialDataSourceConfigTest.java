package dev.agentspan.runtime.credentials;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import dev.agentspan.runtime.AgentRuntime;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CredentialDataSourceConfigTest {

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate credentialJdbc;

    @Test
    void schemaIsCreated_usersTableExists() {
        Integer count = credentialJdbc.queryForObject(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users'",
            java.util.Map.of(), Integer.class);
        assertThat(count).isEqualTo(1);
    }

    @Test
    void schemaIsCreated_allFourTablesExist() {
        for (String table : java.util.List.of(
                "users", "api_keys", "credentials_store", "credentials_binding")) {
            Integer count = credentialJdbc.queryForObject(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=:t",
                java.util.Map.of("t", table), Integer.class);
            assertThat(count).as("table %s should exist", table).isEqualTo(1);
        }
    }
}
