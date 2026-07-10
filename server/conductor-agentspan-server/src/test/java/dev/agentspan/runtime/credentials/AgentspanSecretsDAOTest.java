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
 * {@link AgentspanSecretsDAO} bridges conductor's global {@code SecretsDAO} to AgentSpan's per-user
 * {@link CredentialStoreProvider}, scoped to the anonymous/system user. Verifies the name→value
 * round-trip is scoped to {@code ANONYMOUS_USER_ID} (so other users' secrets are invisible) and that
 * the bean is selected only by {@code conductor.secrets.type=agentspan}.
 */
class AgentspanSecretsDAOTest {

    private static final String ANON = "00000000-0000-0000-0000-000000000000";

    /** In-memory {@link CredentialStoreProvider} keyed by (userId,name) so scope can be asserted. */
    static class FakeStore implements CredentialStoreProvider {
        final Map<String, String> data = new LinkedHashMap<>();

        private static String k(String u, String n) {
            return u + "|" + n;
        }

        @Override
        public String get(String userId, String name) {
            return data.get(k(userId, name));
        }

        @Override
        public void set(String userId, String name, String value) {
            data.put(k(userId, name), value);
        }

        @Override
        public void delete(String userId, String name) {
            data.remove(k(userId, name));
        }

        @Override
        public List<CredentialMeta> list(String userId) {
            List<CredentialMeta> out = new ArrayList<>();
            for (String key : data.keySet()) {
                int bar = key.indexOf('|');
                if (key.substring(0, bar).equals(userId)) {
                    out.add(CredentialMeta.builder().name(key.substring(bar + 1)).build());
                }
            }
            return out;
        }
    }

    @Test
    void roundTrip_scopedToAnonymousUser() {
        FakeStore store = new FakeStore();
        AgentspanSecretsDAO dao = new AgentspanSecretsDAO(store);

        assertThat(dao.secretExists("GITHUB_TOKEN")).isFalse();
        assertThat(dao.getSecret("GITHUB_TOKEN")).isNull();

        dao.putSecret("GITHUB_TOKEN", "ghp_x");
        // written under the anonymous/system user — the scope conductor resolves against
        assertThat(store.data).containsEntry(ANON + "|GITHUB_TOKEN", "ghp_x");
        assertThat(dao.getSecret("GITHUB_TOKEN")).isEqualTo("ghp_x");
        assertThat(dao.secretExists("GITHUB_TOKEN")).isTrue();

        dao.putSecret("SLACK_TOKEN", "xoxb");
        assertThat(dao.listSecretNames()).containsExactlyInAnyOrder("GITHUB_TOKEN", "SLACK_TOKEN");

        dao.deleteSecret("GITHUB_TOKEN");
        assertThat(dao.getSecret("GITHUB_TOKEN")).isNull();
        assertThat(dao.listSecretNames()).containsExactly("SLACK_TOKEN");
    }

    @Test
    void doesNotReadOtherUsersSecrets() {
        FakeStore store = new FakeStore();
        store.set("some-other-user", "GITHUB_TOKEN", "not-mine");
        AgentspanSecretsDAO dao = new AgentspanSecretsDAO(store);
        assertThat(dao.getSecret("GITHUB_TOKEN")).isNull();
        assertThat(dao.listSecretNames()).isEmpty();
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
