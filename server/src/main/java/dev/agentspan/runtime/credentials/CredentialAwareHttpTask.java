/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;
import com.netflix.conductor.tasks.http.HttpTask;
import com.netflix.conductor.tasks.http.providers.RestTemplateProvider;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Extends Conductor's HttpTask to resolve ${NAME} credential placeholders
 * in HTTP headers before execution.
 *
 * <p>Resolution uses {@link CredentialResolutionService} with the userId from
 * the execution token in {@code __agentspan_ctx__}. Resolved values exist
 * only in memory during execution — they are never persisted to the task model.</p>
 */
public class CredentialAwareHttpTask extends HttpTask {

    private static final Logger log = LoggerFactory.getLogger(CredentialAwareHttpTask.class);
    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{(\\w+)}");

    private final ExecutionTokenService tokenService;
    private final CredentialResolutionService resolutionService;

    public CredentialAwareHttpTask(
            RestTemplateProvider restTemplateProvider,
            ObjectMapper objectMapper,
            ExecutionTokenService tokenService,
            CredentialResolutionService resolutionService) {
        super(restTemplateProvider, objectMapper);
        this.tokenService = tokenService;
        this.resolutionService = resolutionService;
    }

    @Override
    @SuppressWarnings("unchecked")
    public void start(WorkflowModel workflow, TaskModel task, WorkflowExecutor executor) {
        Map<String, Object> input = task.getInputData();
        Object httpRequest = input.get("http_request");
        Object ctx = input.get("__agentspan_ctx__");

        if (httpRequest instanceof Map<?,?> reqMap && ctx != null) {
            Object headers = reqMap.get("headers");
            if (headers instanceof Map<?,?> headerMap && containsPlaceholders(headerMap)) {
                String userId = extractUserId(ctx);
                if (userId != null) {
                    Map<String, String> resolved = resolveHeadersForUser(
                        (Map<String, String>) headerMap, userId);
                    ((Map<String, Object>) reqMap).put("headers", resolved);
                }
            }
        }

        super.start(workflow, task, executor);
    }

    /**
     * Resolve ${NAME} placeholders in header values using the credential store.
     * Package-private for testing.
     */
    Map<String, String> resolveHeadersForUser(Map<String, String> headers, String userId) {
        Map<String, String> result = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            String value = entry.getValue();
            Matcher m = PLACEHOLDER.matcher(value);
            StringBuilder sb = new StringBuilder();
            while (m.find()) {
                String credName = m.group(1);
                String credValue = resolutionService.resolve(userId, credName);
                m.appendReplacement(sb, Matcher.quoteReplacement(
                    credValue != null ? credValue : ""));
            }
            m.appendTail(sb);
            result.put(entry.getKey(), sb.toString());
        }
        return result;
    }

    private String extractUserId(Object ctx) {
        String token = null;
        if (ctx instanceof Map<?,?> ctxMap) {
            token = (String) ctxMap.get("execution_token");
        } else if (ctx instanceof String s) {
            token = s;
        }
        if (token == null) return null;
        try {
            return tokenService.validate(token).userId();
        } catch (Exception e) {
            log.warn("Failed to validate token for header resolution: {}", e.getMessage());
            return null;
        }
    }

    private boolean containsPlaceholders(Map<?,?> headers) {
        for (Object v : headers.values()) {
            if (v != null && PLACEHOLDER.matcher(String.valueOf(v)).find()) return true;
        }
        return false;
    }
}
