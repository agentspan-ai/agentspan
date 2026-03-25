package dev.agentspan.runtime.auth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import dev.agentspan.runtime.AgentRuntime;

import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class ApiKeyRepositoryTest {

    @Autowired
    private ApiKeyRepository apiKeyRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private User testUser;

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM api_keys WHERE label LIKE 'test_%'", Map.of());
        jdbc.update("DELETE FROM users WHERE username = 'apikey_test_user'", Map.of());
        testUser = userRepository.create("apikey_test_user", "API Key Test", null, "pw");
    }

    @Test
    void findUserByKey_returnsEmpty_whenKeyUnknown() {
        assertThat(apiKeyRepository.findUserByKey("asp_nonexistent")).isEmpty();
    }

    @Test
    void createKey_andLookupByRawKey_returnsUser() {
        String rawKey = apiKeyRepository.createKey(testUser.getId(), "test_my-key");

        assertThat(rawKey).startsWith("asp_");

        Optional<User> found = apiKeyRepository.findUserByKey(rawKey);
        assertThat(found).isPresent();
        assertThat(found.get().getId()).isEqualTo(testUser.getId());
    }

    @Test
    void findUserByKey_updatesLastUsedAt() throws InterruptedException {
        String rawKey = apiKeyRepository.createKey(testUser.getId(), "test_ts-key");

        Thread.sleep(10);
        apiKeyRepository.findUserByKey(rawKey);

        String lastUsed = jdbc.queryForObject(
            "SELECT last_used_at FROM api_keys WHERE label = 'test_ts-key'",
            Map.of(), String.class);
        assertThat(lastUsed).isNotNull();
    }
}
