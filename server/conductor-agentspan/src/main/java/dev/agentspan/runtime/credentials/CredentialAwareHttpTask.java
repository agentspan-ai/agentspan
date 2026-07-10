/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;
import com.netflix.conductor.tasks.http.HttpTask;
import com.netflix.conductor.tasks.http.providers.RestTemplateProvider;

/**
 * Extends Conductor's HttpTask to resolve credential placeholders in HTTP
 * headers before execution.  Placeholders arrive as {@code #{NAME}} because
 * {@link dev.agentspan.runtime.compiler.ToolCompiler} converts the SDK's
 * {@code ${NAME}} syntax so that Conductor's own {@code ${...}} parameter
 * resolution does not consume them.
 *
 * <p>Resolution uses {@link CredentialResolutionService} against the global credential
 * store. Resolved values exist only in memory during execution — they are never persisted
 * to the task model.</p>
 */
public class CredentialAwareHttpTask extends HttpTask {

    private static final Logger log = LoggerFactory.getLogger(CredentialAwareHttpTask.class);
    private static final Pattern PLACEHOLDER = Pattern.compile("#\\{([\\w.]+)}");
    private final CredentialResolutionService resolutionService;

    public CredentialAwareHttpTask(
            RestTemplateProvider restTemplateProvider,
            ObjectMapper objectMapper,
            CredentialResolutionService resolutionService) {
        super(restTemplateProvider, objectMapper);
        this.resolutionService = resolutionService;
    }

    @Override
    @SuppressWarnings("unchecked")
    public void start(WorkflowModel workflow, TaskModel task, WorkflowExecutor executor) {
        Map<String, Object> input = task.getInputData();
        Object httpRequest = input.get("http_request");

        Map<String, String> originalHeaders = null;

        if (httpRequest instanceof Map<?, ?> reqMap) {
            Object headers = reqMap.get("headers");
            if (headers instanceof Map<?, ?> headerMap && containsPlaceholders(headerMap)) {
                originalHeaders = new LinkedHashMap<>((Map<String, String>) headerMap);
                Map<String, String> resolved = resolveHeaders((Map<String, String>) headerMap);
                ((Map<String, Object>) reqMap).put("headers", resolved);
            }
        }

        try {
            super.start(workflow, task, executor);
        } finally {
            // Restore placeholder headers so resolved credentials are never persisted.
            if (originalHeaders != null && httpRequest instanceof Map<?, ?> reqMap) {
                ((Map<String, Object>) reqMap).put("headers", originalHeaders);
            }
        }
    }

    /**
     * Resolve #{NAME} placeholders in header values using the credential store.
     * Package-private for testing.
     */
    Map<String, String> resolveHeaders(Map<String, String> headers) {
        Map<String, String> result = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            String value = entry.getValue();
            Matcher m = PLACEHOLDER.matcher(value);
            StringBuilder sb = new StringBuilder();
            while (m.find()) {
                String credName = m.group(1);
                String credValue = resolutionService.resolve(credName);
                m.appendReplacement(sb, Matcher.quoteReplacement(credValue != null ? credValue : ""));
            }
            m.appendTail(sb);
            result.put(entry.getKey(), sb.toString());
        }
        return result;
    }

    private boolean containsPlaceholders(Map<?, ?> headers) {
        for (Object v : headers.values()) {
            if (v != null && PLACEHOLDER.matcher(String.valueOf(v)).find()) return true;
        }
        return false;
    }
}
