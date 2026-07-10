/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

import dev.agentspan.runtime.model.credentials.CredentialMeta;
import dev.agentspan.runtime.spi.CredentialStoreProvider;

/**
 * {@link AgentspanSecretsDAO} bridges conductor's global {@code SecretsDAO} to AgentSpan's
 * (single-scope) {@link CredentialStoreProvider}. Verifies the name→value round-trip and that the
 * bean is selected only by {@code conductor.secrets.type=agentspan}.
 */
class AgentspanSecretsDAOTest {

    /** In-memory {@link CredentialStoreProvider} keyed by name (the store is global — no userId). */
    static class FakeStore implements CredentialStoreProvider {
        final Map<String, String> data = new LinkedHashMap<>();

        @Override
        public String get(String name) {
            return data.get(name);
        }

        @Override
        public void set(String name, String value) {
            data.put(name, value);
        }

        @Override
        public void delete(String name) {
            data.remove(name);
        }

        @Override
        public List<CredentialMeta> list() {
            List<CredentialMeta> out = new ArrayList<>();
            for (String name : data.keySet()) {
                out.add(CredentialMeta.builder().name(name).build());
            }
            return out;
        }
    }

    @Test
    void roundTrip() {
        FakeStore store = new FakeStore();
        AgentspanSecretsDAO dao = new AgentspanSecretsDAO(store);

        assertThat(dao.secretExists("GITHUB_TOKEN")).isFalse();
        assertThat(dao.getSecret("GITHUB_TOKEN")).isNull();

        dao.putSecret("GITHUB_TOKEN", "ghp_x");
        assertThat(store.data).containsEntry("GITHUB_TOKEN", "ghp_x");
        assertThat(dao.getSecret("GITHUB_TOKEN")).isEqualTo("ghp_x");
        assertThat(dao.secretExists("GITHUB_TOKEN")).isTrue();

        dao.putSecret("SLACK_TOKEN", "xoxb");
        assertThat(dao.listSecretNames()).containsExactlyInAnyOrder("GITHUB_TOKEN", "SLACK_TOKEN");

        dao.deleteSecret("GITHUB_TOKEN");
        assertThat(dao.getSecret("GITHUB_TOKEN")).isNull();
        assertThat(dao.listSecretNames()).containsExactly("SLACK_TOKEN");
    }

    // ── gating: selected only by conductor.secrets.type=agentspan ──

    @Configuration
    @Import(AgentspanSecretsDAO.class)
    static class DaoConfig {}

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withBean(CredentialStoreProvider.class, () -> mock(CredentialStoreProvider.class))
            .withUserConfiguration(DaoConfig.class);

    @Test
    void beanPresent_whenConductorSecretsTypeAgentspan() {
        runner.withPropertyValues("conductor.secrets.type=agentspan")
                .run(ctx -> assertThat(ctx).hasSingleBean(AgentspanSecretsDAO.class));
    }

    @Test
    void beanAbsent_whenFlagUnsetOrDifferent() {
        runner.run(ctx -> assertThat(ctx).doesNotHaveBean(AgentspanSecretsDAO.class));
        runner.withPropertyValues("conductor.secrets.type=env")
                .run(ctx -> assertThat(ctx).doesNotHaveBean(AgentspanSecretsDAO.class));
    }
}
