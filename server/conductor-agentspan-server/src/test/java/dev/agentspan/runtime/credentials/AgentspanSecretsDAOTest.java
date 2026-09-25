/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;
import dev.agentspan.runtime.model.credentials.CredentialMeta;

/**
 * {@link AgentspanSecretsDAO} is conductor's global {@code SecretsDAO} backed directly by the
 * AES-256-GCM encrypted {@code credentials_store} table — the single storage backend for
 * conductor's own secret substitution AND AgentSpan's own credential surfaces (Credentials UI,
 * resolution service, env seeder). Verifies the encrypted round-trip against a real DB and that
 * the bean is selected only by {@code conductor.secrets.type=agentspan}.
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class AgentspanSecretsDAOTest {

    @Autowired
    private AgentspanSecretsDAO dao;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String USER_ID = "00000000-0000-0000-0000-000000000000";

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM credentials_store WHERE user_id = :uid", Map.of("uid", USER_ID));
    }

    @Test
    void putSecret_andGetSecret_roundTripsEncryptedValue() {
        dao.putSecret("GITHUB_TOKEN", "ghp_supersecret");
        assertThat(dao.getSecret("GITHUB_TOKEN")).isEqualTo("ghp_supersecret");
    }

    @Test
    void getSecret_returnsNull_whenNotFound() {
        assertThat(dao.getSecret("DOES_NOT_EXIST")).isNull();
    }

    @Test
    void secretExists_reflectsPresence() {
        assertThat(dao.secretExists("GITHUB_TOKEN")).isFalse();
        dao.putSecret("GITHUB_TOKEN", "ghp_x");
        assertThat(dao.secretExists("GITHUB_TOKEN")).isTrue();
    }

    @Test
    void deleteSecret_removesCredential() {
        dao.putSecret("TO_DELETE", "value");
        dao.deleteSecret("TO_DELETE");
        assertThat(dao.getSecret("TO_DELETE")).isNull();
    }

    @Test
    void listSecretNames_returnsAllNames() {
        dao.putSecret("GITHUB_TOKEN", "ghp_x");
        dao.putSecret("SLACK_TOKEN", "xoxb");

        assertThat(dao.listSecretNames()).containsExactlyInAnyOrder("GITHUB_TOKEN", "SLACK_TOKEN");
    }

    @Test
    void listWithMeta_returnsPartialValues_notPlaintext() {
        dao.putSecret("OPENAI_KEY", "sk-abcdefghijklmnop");

        List<CredentialMeta> list = dao.listWithMeta();

        CredentialMeta meta = list.stream()
                .filter(m -> m.getName().equals("OPENAI_KEY"))
                .findFirst()
                .orElseThrow();

        // Partial: first 4 + ... + last 4
        assertThat(meta.getPartial()).isEqualTo("sk-a...mnop");
        assertThat(meta.getUpdatedAt()).isNotNull();
        // Plaintext is NOT in the list response
        assertThat(meta.toString()).doesNotContain("abcdefghijklmnop");
    }

    @Test
    void putSecret_updatesExistingCredential() {
        dao.putSecret("MY_KEY", "original");
        dao.putSecret("MY_KEY", "updated");
        assertThat(dao.getSecret("MY_KEY")).isEqualTo("updated");
    }

    @Test
    void encryptedValueInDb_isNotPlaintext() {
        dao.putSecret("SECRET", "plaintext_value");

        // Read raw bytes from DB
        byte[] raw = jdbc.queryForObject(
                "SELECT encrypted_value FROM credentials_store WHERE user_id=:uid AND name=:n",
                Map.of("uid", USER_ID, "n", "SECRET"),
                byte[].class);

        assertThat(raw).isNotNull();
        assertThat(new String(raw)).doesNotContain("plaintext_value");
    }

    // ── gating: selected only by conductor.secrets.type=agentspan ──

    @Configuration
    @Import(AgentspanSecretsDAO.class)
    static class DaoConfig {}

    private final ApplicationContextRunner gatingRunner = new ApplicationContextRunner()
            .withBean("credentialJdbc", NamedParameterJdbcTemplate.class, () -> mock(NamedParameterJdbcTemplate.class))
            .withBean("credentialMasterKey", byte[].class, () -> new byte[32])
            .withUserConfiguration(DaoConfig.class);

    @Test
    void beanPresent_whenConductorSecretsTypeAgentspan() {
        gatingRunner.withPropertyValues("conductor.secrets.type=agentspan").run(ctx -> assertThat(ctx)
                .hasSingleBean(AgentspanSecretsDAO.class));
    }

    @Test
    void beanAbsent_whenFlagUnsetOrDifferent() {
        gatingRunner.run(ctx -> assertThat(ctx).doesNotHaveBean(AgentspanSecretsDAO.class));
        gatingRunner.withPropertyValues("conductor.secrets.type=env").run(ctx -> assertThat(ctx)
                .doesNotHaveBean(AgentspanSecretsDAO.class));
    }
}
