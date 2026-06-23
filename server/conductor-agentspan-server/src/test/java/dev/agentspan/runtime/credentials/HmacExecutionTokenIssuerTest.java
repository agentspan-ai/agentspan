/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.List;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import dev.agentspan.runtime.spi.ExecutionTokenIssuer;

class HmacExecutionTokenIssuerTest {

    private byte[] masterKey;
    private HmacExecutionTokenIssuer service;

    @BeforeEach
    void setUp() {
        masterKey = new byte[32];
        new SecureRandom().nextBytes(masterKey);
        service = new HmacExecutionTokenIssuer(() -> masterKey);
    }

    @Test
    void mintAndValidate_validToken_returnsPayload() {
        String token = service.mint("user-123", "wf-456", List.of("GITHUB_TOKEN"), 3600);

        ExecutionTokenIssuer.TokenPayload payload = service.validate(token);

        assertThat(payload.userId()).isEqualTo("user-123");
        assertThat(payload.executionId()).isEqualTo("wf-456");
        assertThat(payload.declaredNames()).containsExactly("GITHUB_TOKEN");
    }

    @Test
    void validate_expiredToken_throws() throws Exception {
        // mint() enforces max(3600, ttl), so we can't get a sub-3600s token via mint().
        // Instead, forge a structurally valid token with exp set to the past.
        String header = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString("{\"alg\":\"HS256\",\"typ\":\"JWT\"}".getBytes(StandardCharsets.UTF_8));
        long pastExp = Instant.now().minusSeconds(3600).getEpochSecond();
        String payloadJson = "{\"jti\":\"test-jti\",\"sub\":\"user-1\",\"wid\":\"wf-1\"," + "\"iat\":"
                + (pastExp - 3600) + ",\"exp\":" + pastExp + "," + "\"scope\":\"credentials\",\"declared_names\":[]}";
        String payloadB64 =
                Base64.getUrlEncoder().withoutPadding().encodeToString(payloadJson.getBytes(StandardCharsets.UTF_8));
        String signingInput = header + "." + payloadB64;
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(masterKey, "HmacSHA256"));
        String sig = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(mac.doFinal(signingInput.getBytes(StandardCharsets.UTF_8)));
        String token = signingInput + "." + sig;

        assertThatThrownBy(() -> service.validate(token))
                .isInstanceOf(ExecutionTokenIssuer.TokenExpiredException.class);
    }

    @Test
    void validate_tamperedSignature_throws() {
        String token = service.mint("user-1", "wf-1", List.of("KEY_A"), 3600);
        // Tamper last character of signature
        String tampered = token.substring(0, token.length() - 1) + "X";

        assertThatThrownBy(() -> service.validate(tampered))
                .isInstanceOf(ExecutionTokenIssuer.TokenInvalidException.class);
    }

    @Test
    void validate_tamperedPayload_throws() {
        String token = service.mint("user-1", "wf-1", List.of(), 3600);
        String[] parts = token.split("\\.");
        // Replace payload with a different base64
        String fakePayload = java.util.Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString("{\"sub\":\"attacker\",\"scope\":\"credentials\"}".getBytes());
        String tampered = parts[0] + "." + fakePayload + "." + parts[2];

        assertThatThrownBy(() -> service.validate(tampered))
                .isInstanceOf(ExecutionTokenIssuer.TokenInvalidException.class);
    }

    @Test
    void revoke_invalidatesToken() {
        String token = service.mint("user-1", "wf-1", List.of(), 3600);
        ExecutionTokenIssuer.TokenPayload payload = service.validate(token);

        service.revoke(payload.jti(), payload.exp());

        assertThatThrownBy(() -> service.validate(token))
                .isInstanceOf(ExecutionTokenIssuer.TokenRevokedException.class);
    }

    @Test
    void mint_usesMaxTtl_forLongRunningExecution() {
        // execution_timeout=6000 → exp should be ~6000s from now, not 1h
        String token = service.mint("u", "wf", List.of(), 6000);
        ExecutionTokenIssuer.TokenPayload payload = service.validate(token);

        long ttl = payload.exp() - Instant.now().getEpochSecond();
        assertThat(ttl).isGreaterThan(5000); // roughly 6000s
    }

    @Test
    void validate_sameKey_succeeds() throws Exception {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        HmacExecutionTokenIssuer issuer = new HmacExecutionTokenIssuer(() -> key);
        HmacExecutionTokenIssuer otherIssuer = new HmacExecutionTokenIssuer(() -> key); // same key
        String token = otherIssuer.mint("u", "wf", List.of(), 3600);
        // This should pass (same key)
        assertThatCode(() -> issuer.validate(token)).doesNotThrowAnyException();
    }
}
