// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.conductoross.conductor.ai.exceptions.CredentialAuthException;
import org.conductoross.conductor.ai.exceptions.CredentialNotFoundException;
import org.conductoross.conductor.ai.exceptions.CredentialRateLimitException;
import org.conductoross.conductor.ai.exceptions.CredentialServiceException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.fasterxml.jackson.core.type.TypeReference;
import com.netflix.conductor.client.exception.ConductorClientException;
import com.netflix.conductor.client.http.ConductorClient;
import com.netflix.conductor.client.http.ConductorClientRequest;
import com.netflix.conductor.client.http.ConductorClientRequest.Method;

/**
 * Resolves declared secret values from the AgentSpan server ({@code POST
 * /api/workers/secrets}) using a worker execution token, over the shared native
 * Conductor {@link ConductorClient}/ApiClient (same HTTP + token-auth backend as
 * every other client). Mirrors Python's {@code WorkerCredentialFetcher}.
 *
 * <p>Java is tier-1-only per {@code docs/design/secret-injection-contract.md} §6
 * rule 1: {@code System.getenv()} is immutable at runtime. The fetcher returns
 * values to the caller, who passes them to tool handlers via
 * {@code ToolContext#getCredential}.
 *
 * <p>Error contract — every failure mode produces a typed exception. Conductor's
 * {@link ConductorClientException} (raised on non-2xx) is mapped by HTTP status.
 */
public class WorkerCredentialFetcher {

    private static final Logger logger = LoggerFactory.getLogger(WorkerCredentialFetcher.class);

    private static final TypeReference<Map<String, String>> SECRETS_TYPE = new TypeReference<Map<String, String>>() {};

    private final ConductorClient client;

    public WorkerCredentialFetcher(ConductorClient client) {
        this.client = client;
    }

    /**
     * Resolve {@code names} via {@code POST /api/workers/secrets} using
     * {@code executionToken}.
     *
     * @throws CredentialNotFoundException token absent, or server returned 200
     *         with some names missing
     * @throws CredentialAuthException token rejected (401)
     * @throws CredentialRateLimitException 429
     * @throws CredentialServiceException 5xx/4xx or network failure
     */
    public Map<String, String> fetch(String executionToken, List<String> names) {
        if (names == null || names.isEmpty()) return Collections.emptyMap();
        if (executionToken == null || executionToken.isBlank()) {
            throw new CredentialNotFoundException(names);
        }

        ConductorClientRequest request = ConductorClientRequest.builder()
                .method(Method.POST)
                .path("/workers/secrets")
                .body(Map.of("token", executionToken, "names", names))
                .build();

        Map<String, String> resolved;
        try {
            resolved = client.execute(request, SECRETS_TYPE).getData();
        } catch (ConductorClientException e) {
            int status = e.getStatus();
            if (status == 401) throw new CredentialAuthException(e.getMessage());
            if (status == 429) throw new CredentialRateLimitException();
            logger.error("Credential service error ({}): {}", status, e.getMessage());
            throw new CredentialServiceException(status, e.getMessage());
        }
        if (resolved == null) resolved = new LinkedHashMap<>();

        List<String> missing = new ArrayList<>();
        for (String name : names) {
            if (!resolved.containsKey(name)) missing.add(name);
        }
        if (!missing.isEmpty()) {
            logger.error("Credentials not found on server: {}", missing);
            throw new CredentialNotFoundException(missing);
        }
        return resolved;
    }
}
