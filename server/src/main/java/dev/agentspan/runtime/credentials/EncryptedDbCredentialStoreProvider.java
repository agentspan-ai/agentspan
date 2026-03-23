/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import dev.agentspan.runtime.model.credentials.CredentialMeta;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.ByteBuffer;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * AES-256-GCM encrypted credential store backed by the credential SQLite/Postgres DB.
 *
 * <p>Encryption format: [12-byte IV][ciphertext+16-byte GCM tag]
 * All concatenated into a single BLOB stored in credentials_store.encrypted_value.</p>
 *
 * <p>The master key is the 32-byte key from {@code MasterKeyConfig#credentialMasterKey()}.</p>
 */
@Component
public class EncryptedDbCredentialStoreProvider implements CredentialStoreProvider {

    private static final Logger log = LoggerFactory.getLogger(EncryptedDbCredentialStoreProvider.class);
    private static final String ALGORITHM = "AES/GCM/NoPadding";
    private static final int IV_LENGTH  = 12; // GCM standard nonce
    private static final int TAG_LENGTH = 128; // GCM auth tag bits
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    private final NamedParameterJdbcTemplate jdbc;
    private final byte[] masterKey;

    public EncryptedDbCredentialStoreProvider(
            @Qualifier("credentialJdbc") NamedParameterJdbcTemplate jdbc,
            @Qualifier("credentialMasterKey") byte[] masterKey) {
        this.jdbc = jdbc;
        this.masterKey = masterKey;
    }

    @Override
    public String get(String userId, String name) {
        try {
            byte[] encrypted = jdbc.queryForObject(
                "SELECT encrypted_value FROM credentials_store " +
                "WHERE user_id = :uid AND name = :n",
                Map.of("uid", userId, "n", name), byte[].class);
            if (encrypted == null) return null;
            return decrypt(encrypted);
        } catch (org.springframework.dao.EmptyResultDataAccessException e) {
            return null;
        } catch (Exception e) {
            log.error("Failed to decrypt credential '{}' for user '{}': {}", name, userId, e.getMessage());
            throw new IllegalStateException("Failed to decrypt credential: " + name, e);
        }
    }

    @Override
    public void set(String userId, String name, String value) {
        try {
            byte[] encrypted = encrypt(value);
            String now = Instant.now().toString();
            int updated = jdbc.update(
                "UPDATE credentials_store SET encrypted_value = :enc, updated_at = :now " +
                "WHERE user_id = :uid AND name = :n",
                Map.of("enc", encrypted, "uid", userId, "n", name, "now", now));
            if (updated == 0) {
                jdbc.update(
                    "INSERT INTO credentials_store (user_id, name, encrypted_value, created_at, updated_at) " +
                    "VALUES (:uid, :n, :enc, :now, :now)",
                    Map.of("uid", userId, "n", name, "enc", encrypted, "now", now));
            }
        } catch (Exception e) {
            throw new IllegalStateException("Failed to store credential: " + name, e);
        }
    }

    @Override
    public void delete(String userId, String name) {
        jdbc.update("DELETE FROM credentials_store WHERE user_id = :uid AND name = :n",
            Map.of("uid", userId, "n", name));
    }

    @Override
    public List<CredentialMeta> list(String userId) {
        // Include encrypted_value in the SELECT so we can decrypt it inline without
        // opening a second JDBC connection (SQLite pool has maximumPoolSize=1;
        // calling get() from inside a RowMapper would exhaust the pool).
        return jdbc.query(
            "SELECT name, encrypted_value, created_at, updated_at " +
            "FROM credentials_store WHERE user_id = :uid ORDER BY name",
            Map.of("uid", userId),
            (rs, row) -> {
                String name = rs.getString("name");
                byte[] enc = rs.getBytes("encrypted_value");
                String partial;
                try {
                    partial = toPartial(enc != null ? decrypt(enc) : null);
                } catch (Exception e) {
                    partial = "????...????";
                }
                return CredentialMeta.builder()
                    .name(name)
                    .partial(partial)
                    .createdAt(parseInstant(rs.getString("created_at")))
                    .updatedAt(parseInstant(rs.getString("updated_at")))
                    .build();
            });
    }

    // ── Encryption ────────────────────────────────────────────────────

    private byte[] encrypt(String plaintext) throws Exception {
        byte[] iv = new byte[IV_LENGTH];
        SECURE_RANDOM.nextBytes(iv);

        SecretKeySpec keySpec = new SecretKeySpec(masterKey, "AES");
        Cipher cipher = Cipher.getInstance(ALGORITHM);
        cipher.init(Cipher.ENCRYPT_MODE, keySpec, new GCMParameterSpec(TAG_LENGTH, iv));
        byte[] ciphertext = cipher.doFinal(plaintext.getBytes(java.nio.charset.StandardCharsets.UTF_8));

        // Format: [IV 12 bytes][ciphertext+tag]
        ByteBuffer buf = ByteBuffer.allocate(IV_LENGTH + ciphertext.length);
        buf.put(iv);
        buf.put(ciphertext);
        return buf.array();
    }

    private String decrypt(byte[] data) throws Exception {
        ByteBuffer buf = ByteBuffer.wrap(data);
        byte[] iv = new byte[IV_LENGTH];
        buf.get(iv);
        byte[] ciphertext = new byte[buf.remaining()];
        buf.get(ciphertext);

        SecretKeySpec keySpec = new SecretKeySpec(masterKey, "AES");
        Cipher cipher = Cipher.getInstance(ALGORITHM);
        cipher.init(Cipher.DECRYPT_MODE, keySpec, new GCMParameterSpec(TAG_LENGTH, iv));
        byte[] plaintext = cipher.doFinal(ciphertext);
        return new String(plaintext, java.nio.charset.StandardCharsets.UTF_8);
    }

    // ── Helpers ───────────────────────────────────────────────────────

    /**
     * Return first 4 + "..." + last 4 characters.
     * Consistent with OpenAI, GitHub, AWS key display conventions.
     */
    static String toPartial(String value) {
        if (value == null || value.length() < 8) return "****...****";
        return value.substring(0, 4) + "..." + value.substring(value.length() - 4);
    }

    private Instant parseInstant(String s) {
        if (s == null) return null;
        try { return Instant.parse(s); }
        catch (Exception e) { return null; }
    }
}
