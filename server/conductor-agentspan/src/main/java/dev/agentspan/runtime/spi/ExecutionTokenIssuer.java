/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.spi;

import java.util.List;

/**
 * Strategy interface for minting, validating and revoking the short-lived execution tokens that
 * authorize a worker to resolve a bounded set of credentials for one execution.
 *
 * <p>The standalone server ships an HMAC-SHA256 implementation signed with the master key and an
 * in-memory jti deny-list; an embedding host (e.g. orkes-conductor) can supply an asymmetric or
 * KMS-backed signer and a durable (e.g. Redis) revocation list. The token wire format is an
 * implementation concern — callers only depend on this contract and {@link TokenPayload}.</p>
 */
public interface ExecutionTokenIssuer {

    /**
     * Mint a new execution token.
     *
     * @param userId         the authenticated user's ID (or username for login tokens)
     * @param executionId    the execution ID (or "login" for login tokens)
     * @param declaredNames  credential names declared by the agent (bounds resolution)
     * @param executionTimeoutSeconds execution timeout; TTL = max(3600, executionTimeoutSeconds)
     * @return signed token string
     */
    String mint(String userId, String executionId, List<String> declaredNames, long executionTimeoutSeconds);

    /**
     * Validate a token and return its payload.
     *
     * @throws TokenExpiredException  if exp is in the past
     * @throws TokenRevokedException  if jti is in the deny-list
     * @throws TokenInvalidException  if signature or structure is invalid
     */
    TokenPayload validate(String token);

    /**
     * Revoke a token by its jti. Called when an execution is cancelled or terminated.
     *
     * @param jti the unique token ID
     * @param exp the token's expiry epoch second (for self-pruning)
     */
    void revoke(String jti, long exp);

    // ── Value types ───────────────────────────────────────────────────

    record TokenPayload(String jti, String userId, String executionId, long exp, List<String> declaredNames) {}

    class TokenInvalidException extends RuntimeException {
        public TokenInvalidException(String msg) {
            super(msg);
        }
    }

    class TokenExpiredException extends RuntimeException {
        public TokenExpiredException(String msg) {
            super(msg);
        }
    }

    class TokenRevokedException extends RuntimeException {
        public TokenRevokedException(String msg) {
            super(msg);
        }
    }
}
