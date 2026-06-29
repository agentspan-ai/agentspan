/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.MethodParameter;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import dev.agentspan.runtime.context.RequestContextHolder;
import dev.agentspan.runtime.spi.SecretOutputMasker;

/**
 * Redacts disclosed credential values from execution-read response bodies.
 *
 * <p>Activates for endpoints that include an {@code executionId} in their URL —
 * specifically, {@code /api/agent/executions/{id}}, its {@code /full},
 * {@code /tasks}, {@code /status} sub-paths, and {@code /api/agent/execution/{id}}.</p>
 *
 * <p><b>Host-owned endpoints.</b> {@code /api/workflow/{id}} is the raw Conductor
 * workflow read, owned by the host — not AgentSpan. Masking it is <b>opt-in</b> via
 * {@code agentspan.credentials.mask-workflow-reads=true} (default {@code false}), so
 * merely embedding this library never mutates a host's workflow responses. AgentSpan's
 * own {@code /api/agent/*} reads are always masked.</p>
 *
 * <p>How it works:</p>
 * <ol>
 *   <li>Extract {@code executionId} from the request URI.</li>
 *   <li>Get {@code userId} from the request-scoped {@link RequestContextHolder}.</li>
 *   <li>Serialize the response body to JSON.</li>
 *   <li>Run {@link SecretOutputMasker#mask} over the JSON string — it looks up
 *       the secrets disclosed during this execution and replaces literal
 *       occurrences of their plaintext with {@code ***NAME***}.</li>
 *   <li>Parse the masked JSON back to a {@link JsonNode} so Spring serializes it
 *       in place of the original body.</li>
 * </ol>
 *
 * <p>If anything goes wrong (no execution id, no user, no disclosures, parse
 * error) the body is returned untouched. Masking is best-effort defense in
 * depth — it should never block a response from going out.</p>
 */
@ControllerAdvice
public class CredentialMaskingResponseAdvice implements ResponseBodyAdvice<Object> {

    private static final Logger log = LoggerFactory.getLogger(CredentialMaskingResponseAdvice.class);

    /**
     * Matches execution-read endpoints that may surface task output/data:
     * <ul>
     *   <li>{@code /api/agent/executions/{id}} (+ {@code /full}, {@code /tasks})</li>
     *   <li>{@code /api/agent/execution/{id}}</li>
     *   <li>{@code /api/agent/{id}/status}</li>
     *   <li>{@code /api/workflow/{id}} — raw Conductor workflow read (includeTasks=true)</li>
     * </ul>
     */
    private static final Pattern EXEC_URI = Pattern.compile("^(?:"
            + "/api/agent/(?:execution(?:s)?/([^/]+?)(?:/(?:full|tasks))?|([^/]+?)/status)"
            + "|/api/workflow/([^/?]+)"
            + ")/?$");

    private final SecretOutputMasker masker;
    private final ObjectMapper mapper;

    /**
     * Whether to mask the host-owned {@code /api/workflow/{id}} endpoint. Off by default so the
     * library never mutates an embedding host's raw Conductor responses unless it opts in.
     */
    private final boolean maskWorkflowReads;

    public CredentialMaskingResponseAdvice(
            SecretOutputMasker masker,
            ObjectMapper mapper,
            @Value("${agentspan.credentials.mask-workflow-reads:false}") boolean maskWorkflowReads) {
        this.masker = masker;
        this.mapper = mapper;
        this.maskWorkflowReads = maskWorkflowReads;
    }

    @Override
    public boolean supports(MethodParameter returnType, Class<? extends HttpMessageConverter<?>> converterType) {
        return true; // cheap; URI check in beforeBodyWrite does the real filtering
    }

    @Override
    public Object beforeBodyWrite(
            Object body,
            MethodParameter returnType,
            MediaType selectedContentType,
            Class<? extends HttpMessageConverter<?>> selectedConverterType,
            ServerHttpRequest request,
            ServerHttpResponse response) {

        if (body == null) return null;

        // Skip if not JSON; reserved paths like /stream return SSE
        if (selectedContentType != null && !MediaType.APPLICATION_JSON.includes(selectedContentType)) {
            return body;
        }

        String path = request.getURI().getPath();
        Matcher m = EXEC_URI.matcher(path);
        if (!m.matches()) return body; // not an execution-read endpoint
        // group 1: /agent/executions/{id} or /agent/execution/{id}
        // group 2: /agent/{id}/status
        // group 3: /workflow/{id}
        String executionId = m.group(1) != null ? m.group(1) : m.group(2) != null ? m.group(2) : m.group(3);
        // group 3 = /api/workflow/{id}, a host-owned endpoint. Skip unless explicitly opted in,
        // so embedding the library never mutates the host's raw Conductor workflow responses.
        if (m.group(3) != null && !maskWorkflowReads) return body;
        // exclude reserved sub-paths that happen to match the regex
        if (executionId.equals("prune") || executionId.equals("search")) return body;

        String userId = RequestContextHolder.get().map(c -> c.getUserId()).orElse(null);
        if (userId == null) return body; // anonymous request — nothing to mask against

        try {
            String json = mapper.writeValueAsString(body);
            String masked = masker.mask(executionId, userId, json);
            if (masked == null || masked.equals(json)) return body; // no-op fast path
            return mapper.readTree(masked);
        } catch (Exception e) {
            log.warn("Credential masking skipped for {} ({}): {}", path, executionId, e.toString());
            return body;
        }
    }
}
