/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;
import dev.agentspan.runtime.model.credentials.CredentialMeta;
import dev.agentspan.runtime.spi.CredentialStoreProvider;

@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class EncryptedDbCredentialStoreProviderTest {

    @Autowired
    private CredentialStoreProvider storeProvider;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String USER_ID = "00000000-0000-0000-0000-000000000000";

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM credentials_store WHERE user_id = :uid", Map.of("uid", USER_ID));
    }

    @Test
    void set_andGet_roundTripsEncryptedValue() {
        storeProvider.set("GITHUB_TOKEN", "ghp_supersecret");
        String value = storeProvider.get("GITHUB_TOKEN");
        assertThat(value).isEqualTo("ghp_supersecret");
    }

    @Test
    void get_returnsNull_whenNotFound() {
        assertThat(storeProvider.get("DOES_NOT_EXIST")).isNull();
    }

    @Test
    void delete_removesCredential() {
        storeProvider.set("TO_DELETE", "value");
        storeProvider.delete("TO_DELETE");
        assertThat(storeProvider.get("TO_DELETE")).isNull();
    }

    @Test
    void list_returnsPartialValues_notPlaintext() {
        storeProvider.set("OPENAI_KEY", "sk-abcdefghijklmnop");

        List<CredentialMeta> list = storeProvider.list();

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
    void set_updatesExistingCredential() {
        storeProvider.set("MY_KEY", "original");
        storeProvider.set("MY_KEY", "updated");
        assertThat(storeProvider.get("MY_KEY")).isEqualTo("updated");
    }

    @Test
    void encryptedValueInDb_isNotPlaintext() {
        storeProvider.set("SECRET", "plaintext_value");

        // Read raw bytes from DB
        byte[] raw = jdbc.queryForObject(
                "SELECT encrypted_value FROM credentials_store WHERE user_id=:uid AND name=:n",
                Map.of("uid", USER_ID, "n", "SECRET"),
                byte[].class);

        assertThat(raw).isNotNull();
        assertThat(new String(raw)).doesNotContain("plaintext_value");
    }
}
