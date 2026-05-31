// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.internal;

import ai.agentspan.AgentConfig;
import ai.agentspan.exceptions.CredentialAuthException;
import ai.agentspan.exceptions.CredentialNotFoundException;
import ai.agentspan.exceptions.CredentialRateLimitException;
import ai.agentspan.exceptions.CredentialServiceException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Resolves declared secret values from the AgentSpan server using a worker
 * execution token. Mirrors Python's {@code WorkerCredentialFetcher} and .NET's
 * {@code AgentHttpClient.ResolveCredentialsAsync}.
 *
 * <p>Java is tier-1-only per
 * {@code docs/design/secret-injection-contract.md} §6 rule 1: {@code System.getenv()}
 * is immutable at runtime, so env-injection isn't possible without reflection
 * hacks. The fetcher returns values to the caller, who passes them to tool
 * handlers via {@link ai.agentspan.Credentials}.</p>
 *
 * <p>Error contract — every failure mode produces a typed exception. Silent
 * swallow (the bug class that affected .NET pre-fix) is structurally impossible
 * here.</p>
 */
public class WorkerCredentialFetcher {

    private static final Logger logger = LoggerFactory.getLogger(WorkerCredentialFetcher.class);

    private final AgentConfig config;
    private final HttpApi httpApi;

    public WorkerCredentialFetcher(HttpApi httpApi) {
        this.httpApi = httpApi;
        this.config = httpApi.getConfig();
    }

    /**
     * Resolve {@code names} via {@code POST /api/workers/secrets} using
     * {@code executionToken}.
     *
     * @return name → plaintext value, with every requested name present
     *         (otherwise {@link CredentialNotFoundException} is thrown)
     * @throws CredentialNotFoundException token absent, or server returned 200
     *         with some names missing
     * @throws CredentialAuthException token rejected (401)
     * @throws CredentialRateLimitException 429
     * @throws CredentialServiceException 5xx or network failure
     */
    public Map<String, String> fetch(String executionToken, List<String> names) {
        if (names == null || names.isEmpty()) return Collections.emptyMap();

        if (executionToken == null || executionToken.isBlank()) {
            throw new CredentialNotFoundException(names);
        }

        String url = config.getServerUrl() + "/api/workers/secrets";
        String body = JsonMapper.toJson(Map.of("token", executionToken, "names", names));

        HttpRequest.Builder reqBuilder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body));
        httpApi.addAuthHeaders(reqBuilder);

        HttpResponse<String> resp;
        try {
            resp = httpApi.getRawClient().send(reqBuilder.build(),
                    HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            logger.error("Credential service unreachable: {}", e.toString());
            throw new CredentialServiceException(0, e.toString());
        }

        int status = resp.statusCode();
        if (status == 401) throw new CredentialAuthException(resp.body());
        if (status == 429) throw new CredentialRateLimitException();
        if (status >= 500) throw new CredentialServiceException(status, resp.body());
        if (status >= 400) throw new CredentialServiceException(status, resp.body());

        @SuppressWarnings("unchecked")
        Map<String, String> resolved = (Map<String, String>)
                (Map<?, ?>) JsonMapper.fromJson(resp.body(), Map.class);
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
