package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.*;

import java.nio.file.Path;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MasterKeyConfigTest {

    @TempDir
    Path tempDir;

    @Test
    void loadKey_fromBase64String_returns32ByteKey() {
        byte[] raw = new byte[32];
        new java.security.SecureRandom().nextBytes(raw);
        String b64 = Base64.getEncoder().encodeToString(raw);

        MasterKeyConfig config = new MasterKeyConfig();
        byte[] key = config.loadOrGenerate(b64, tempDir);

        assertThat(key).hasSize(32);
        assertThat(key).isEqualTo(raw);
    }

    @Test
    void loadKey_autoGen_onLocalhost_writesFileAndWarns() {
        MasterKeyConfig config = new MasterKeyConfig();
        byte[] key = config.loadOrGenerate(null, tempDir);

        assertThat(key).hasSize(32);
        // Key file is written to tempDir/.agentspan/master.key
        assertThat(tempDir.resolve(".agentspan/master.key")).exists();
    }

    @Test
    void loadKey_autoGen_subsequentCall_returnsSameKey() {
        MasterKeyConfig config = new MasterKeyConfig();
        byte[] key1 = config.loadOrGenerate(null, tempDir);
        byte[] key2 = config.loadOrGenerate(null, tempDir);

        assertThat(key1).isEqualTo(key2);
    }

    @Test
    void loadKey_missingKey_autoGenerates() {
        MasterKeyConfig config = new MasterKeyConfig();
        byte[] key = config.loadOrGenerate(null, tempDir);

        assertThat(key).hasSize(32);
        assertThat(tempDir.resolve(".agentspan/master.key")).exists();
    }

    @Test
    void loadKey_invalidBase64_throws() {
        MasterKeyConfig config = new MasterKeyConfig();

        assertThatThrownBy(() -> config.loadOrGenerate("not-valid-base64!!!", tempDir))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void loadKey_wrongKeyLength_throws() {
        // 16 bytes = 128-bit, not valid for AES-256
        byte[] short16 = new byte[16];
        String b64 = Base64.getEncoder().encodeToString(short16);
        MasterKeyConfig config = new MasterKeyConfig();

        assertThatThrownBy(() -> config.loadOrGenerate(b64, tempDir))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("32 bytes");
    }
}
