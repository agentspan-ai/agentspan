/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Mints and validates execution tokens for worker credential resolution.
 *
 * <p>Token format: base64url(header).base64url(payload).base64url(hmacSignature)
 * Signed with HMAC-SHA256 using the server master key.</p>
 *
 * <p>jti deny-list: in-memory ConcurrentHashMap (jti → expiryEpochSecond).
 * Self-pruning via scheduled cleanup. In OSS, the deny-list is lost on restart
 * (bounded risk: tokens expire with workflow TTL).</p>
 */
@Service
public class ExecutionTokenService {

    private static final Logger log = LoggerFactory.getLogger(ExecutionTokenService.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final long ONE_HOUR_SECONDS = 3600;
    private static final String SCOPE = "credentials";
    private static final String HEADER = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString("{\"alg\":\"HS256\",\"typ\":\"JWT\"}".getBytes(StandardCharsets.UTF_8));

    private final byte[] masterKey;
    private final ConcurrentHashMap<String, Long> denyList = new ConcurrentHashMap<>();

    public ExecutionTokenService(@Qualifier("credentialMasterKey") byte[] masterKey) {
        this.masterKey = masterKey;
    }

    /**
     * Mint a new execution token.
     *
     * @param userId         the authenticated user's ID (or username for login tokens)
     * @param executionId    the execution ID (or "login" for login tokens)
     * @param declaredNames  credential names declared by the agent (bounds resolution)
     * @param executionTimeoutSeconds execution timeout; TTL = max(3600, executionTimeoutSeconds)
     * @return signed token string
     */
    public String mint(String userId, String executionId, List<String> declaredNames, long executionTimeoutSeconds) {
        long now = Instant.now().getEpochSecond();
        long ttl = Math.max(ONE_HOUR_SECONDS, executionTimeoutSeconds);
        long exp = now + ttl;

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("jti", UUID.randomUUID().toString());
        payload.put("sub", userId);
        payload.put("wid", executionId);
        payload.put("iat", now);
        payload.put("exp", exp);
        payload.put("scope", SCOPE);
        payload.put("declared_names", declaredNames != null ? declaredNames : List.of());

        try {
            String payloadJson = MAPPER.writeValueAsString(payload);
            String payloadB64 = Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(payloadJson.getBytes(StandardCharsets.UTF_8));
            String signingInput = HEADER + "." + payloadB64;
            String sig = hmacSha256B64(signingInput);
            return signingInput + "." + sig;
        } catch (Exception e) {
            throw new IllegalStateException("Failed to mint execution token", e);
        }
    }

    /**
     * Validate a token and return its payload.
     *
     * @throws TokenExpiredException  if exp is in the past
     * @throws TokenRevokedException  if jti is in the deny-list
     * @throws TokenInvalidException  if signature or structure is invalid
     */
    @SuppressWarnings("unchecked")
    public TokenPayload validate(String token) {
        String[] parts = token.split("\\.");
        if (parts.length != 3) {
            throw new TokenInvalidException("Malformed token: expected 3 parts");
        }

        String signingInput = parts[0] + "." + parts[1];
        String expectedSig = hmacSha256B64(signingInput);
        if (!constantTimeEquals(expectedSig, parts[2])) {
            throw new TokenInvalidException("Token signature invalid");
        }

        Map<String, Object> claims;
        try {
            String payloadJson = new String(Base64.getUrlDecoder().decode(parts[1]), StandardCharsets.UTF_8);
            claims = MAPPER.readValue(payloadJson, Map.class);
        } catch (Exception e) {
            throw new TokenInvalidException("Failed to parse token payload");
        }

        long exp = ((Number) claims.get("exp")).longValue();
        if (Instant.now().getEpochSecond() > exp) {
            throw new TokenExpiredException("Token expired");
        }

        String jti = (String) claims.get("jti");
        if (denyList.containsKey(jti)) {
            throw new TokenRevokedException("Token has been revoked (jti=" + jti + ")");
        }

        List<String> names = (List<String>) claims.getOrDefault("declared_names", List.of());
        return new TokenPayload(jti, (String) claims.get("sub"), (String) claims.get("wid"), exp, names);
    }

    /**
     * Revoke a token by adding its jti to the deny-list.
     * Called when an execution is cancelled or terminated.
     *
     * @param jti the unique token ID
     * @param exp the token's expiry epoch second (for self-pruning)
     */
    public void revoke(String jti, long exp) {
        denyList.put(jti, exp);
        log.info("Execution token revoked: jti={}", jti);
    }

    /** Scheduled cleanup of expired deny-list entries (runs every 5 minutes). */
    @Scheduled(fixedRate = 300_000)
    public void pruneExpiredRevocations() {
        long now = Instant.now().getEpochSecond();
        int removed = 0;
        for (Iterator<Map.Entry<String, Long>> it = denyList.entrySet().iterator(); it.hasNext(); ) {
            if (it.next().getValue() < now) {
                it.remove();
                removed++;
            }
        }
        if (removed > 0) {
            log.debug("Pruned {} expired execution token deny-list entries", removed);
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────

    private String hmacSha256B64(String input) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(masterKey, "HmacSHA256"));
            byte[] raw = mac.doFinal(input.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
        } catch (Exception e) {
            throw new IllegalStateException("HMAC-SHA256 failed", e);
        }
    }

    /** Constant-time string comparison to prevent timing attacks. */
    private boolean constantTimeEquals(String a, String b) {
        if (a.length() != b.length()) return false;
        int diff = 0;
        for (int i = 0; i < a.length(); i++) {
            diff |= a.charAt(i) ^ b.charAt(i);
        }
        return diff == 0;
    }

    // ── Value types ───────────────────────────────────────────────────

    public record TokenPayload(String jti, String userId, String executionId, long exp, List<String> declaredNames) {}

    public static class TokenInvalidException extends RuntimeException {
        public TokenInvalidException(String msg) {
            super(msg);
        }
    }

    public static class TokenExpiredException extends RuntimeException {
        public TokenExpiredException(String msg) {
            super(msg);
        }
    }

    public static class TokenRevokedException extends RuntimeException {
        public TokenRevokedException(String msg) {
            super(msg);
        }
    }
}
