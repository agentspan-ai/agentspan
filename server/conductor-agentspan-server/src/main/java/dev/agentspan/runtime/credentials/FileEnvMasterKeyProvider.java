/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.SecureRandom;
import java.util.Base64;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import dev.agentspan.runtime.spi.MasterKeyProvider;

/**
 * OSS file/env implementation of {@link MasterKeyProvider}.
 *
 * <p>Key sourcing rules:</p>
 * <ul>
 *   <li>If {@code AGENTSPAN_MASTER_KEY} env var is set → decode and use it</li>
 *   <li>If unset → auto-generate, persist to ~/.agentspan/master.key, warn</li>
 * </ul>
 *
 * <p>This is the standalone-server default. An embedding host (e.g. orkes-conductor) can source
 * the key from AWS KMS, HashiCorp Vault, Azure Key Vault or GCP KMS by contributing its own
 * {@link MasterKeyProvider} bean in place of this one.</p>
 */
@Component
public class FileEnvMasterKeyProvider implements MasterKeyProvider {

    private static final Logger log = LoggerFactory.getLogger(FileEnvMasterKeyProvider.class);
    private static final int KEY_BYTES = 32; // 256-bit

    private final String masterKeyBase64;
    private volatile byte[] cached;

    public FileEnvMasterKeyProvider(@Value("${AGENTSPAN_MASTER_KEY:#{null}}") String masterKeyBase64) {
        this.masterKeyBase64 = masterKeyBase64;
    }

    @Override
    public byte[] getMasterKey() {
        byte[] result = cached;
        if (result == null) {
            synchronized (this) {
                result = cached;
                if (result == null) {
                    result = loadOrGenerate(masterKeyBase64, Paths.get(System.getProperty("user.home")));
                    cached = result;
                }
            }
        }
        return result;
    }

    /**
     * Package-private for testing — accepts an explicit home directory.
     */
    byte[] loadOrGenerate(String keyBase64, Path homeDir) {
        if (keyBase64 != null && !keyBase64.isBlank()) {
            byte[] decoded;
            try {
                decoded = Base64.getDecoder().decode(keyBase64.trim());
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException("AGENTSPAN_MASTER_KEY is not valid base64: " + e.getMessage(), e);
            }
            if (decoded.length != KEY_BYTES) {
                throw new IllegalArgumentException(
                        "AGENTSPAN_MASTER_KEY must be exactly 32 bytes (256-bit) after base64 decoding, " + "got "
                                + decoded.length + " bytes. Generate with: openssl rand -base64 32");
            }
            log.info("Credential master key loaded from AGENTSPAN_MASTER_KEY");
            return decoded;
        }

        // Key not configured — auto-generate and persist
        return autoGenerate(homeDir);
    }

    private byte[] autoGenerate(Path homeDir) {
        Path keyDir = homeDir.resolve(".agentspan");
        Path keyFile = keyDir.resolve("master.key");

        try {
            if (Files.exists(keyFile)) {
                byte[] existing =
                        Base64.getDecoder().decode(Files.readString(keyFile).trim());
                if (existing.length == KEY_BYTES) {
                    log.warn(
                            "Credential master key loaded from {} — "
                                    + "back up this file; losing it means losing all stored credentials",
                            keyFile);
                    return existing;
                }
                // Corrupt file — regenerate
                log.warn("Existing master.key is invalid, regenerating");
            }

            Files.createDirectories(keyDir);
            byte[] key = new byte[KEY_BYTES];
            new SecureRandom().nextBytes(key);
            String encoded = Base64.getEncoder().encodeToString(key);
            Files.writeString(keyFile, encoded);
            try {
                Files.setPosixFilePermissions(keyFile, PosixFilePermissions.fromString("rw-------"));
            } catch (UnsupportedOperationException ignored) {
                // Non-POSIX filesystem (e.g. Windows) — skip
            }

            log.warn("┌─────────────────────────────────────────────────────────────────┐");
            log.warn("│  AGENTSPAN_MASTER_KEY not set — auto-generated key in use.      │");
            log.warn("│  Credential store key written to: {}  │", keyFile);
            log.warn("│  Back up this file — losing it means losing all credentials.   │");
            log.warn("│  Set AGENTSPAN_MASTER_KEY in production to suppress this.       │");
            log.warn("└─────────────────────────────────────────────────────────────────┘");
            return key;

        } catch (IOException e) {
            throw new IllegalStateException(
                    "Failed to auto-generate credential master key at " + keyFile + ": " + e.getMessage(), e);
        }
    }
}
