/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.conductoross.conductor.ai.mcp.MCPService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.sdk.workflow.executor.task.TaskContext;

import io.modelcontextprotocol.spec.McpSchema;

/**
 * Extends Conductor's {@link MCPService} to resolve credential placeholders
 * in MCP request headers at call time.  Placeholders arrive as {@code #{NAME}}
 * because {@link dev.agentspan.runtime.compiler.ToolCompiler} converts the
 * SDK's {@code ${NAME}} syntax so that Conductor's own {@code ${...}}
 * parameter resolution does not consume them.
 *
 * <p>Resolution happens entirely in memory during the MCP HTTP call.
 * Resolved secrets are NEVER written to the database — the task's persisted
 * {@code inputData} always retains the original {@code #{NAME}} placeholders.
 * This eliminates any window where credentials could leak via the execution
 * API.</p>
 *
 * <p>Uses {@link TaskContext} (set by Conductor's
 * {@code AnnotatedWorkflowSystemTask.execute()}) to read
 * {@code __agentspan_ctx__} from the task input, extract the execution token,
 * and resolve credentials for the owning user.</p>
 */
@Component
@Primary
public class CredentialAwareMcpService extends MCPService {

    private static final Logger log = LoggerFactory.getLogger(CredentialAwareMcpService.class);
    private static final Pattern PLACEHOLDER = Pattern.compile("#\\{(\\w+)}");

    private final ExecutionTokenService tokenService;
    private final CredentialResolutionService resolutionService;

    public CredentialAwareMcpService(
            ExecutionTokenService tokenService, CredentialResolutionService resolutionService) {
        this.tokenService = tokenService;
        this.resolutionService = resolutionService;
    }

    @Override
    public List<McpSchema.Tool> listTools(String serverUrl, Map<String, String> headers) {
        return super.listTools(serverUrl, resolveHeaders(headers));
    }

    @Override
    public Map<String, Object> callTool(
            String serverUrl, String toolName, Map<String, Object> arguments, Map<String, String> headers) {
        return super.callTool(serverUrl, toolName, arguments, resolveHeaders(headers));
    }

    /**
     * Resolve {@code #{NAME}} placeholders in header values using the
     * credential store.  Returns the original headers unchanged if no
     * placeholders are found or if context/token is unavailable.
     */
    private Map<String, String> resolveHeaders(Map<String, String> headers) {
        if (headers == null || headers.isEmpty() || !containsPlaceholders(headers)) {
            return headers;
        }

        String userId = extractUserIdFromTaskContext();
        if (userId == null) {
            log.warn("Cannot resolve MCP credential headers: no userId from TaskContext");
            return headers;
        }

        return resolveHeadersForUser(headers, userId);
    }

    /**
     * Resolve #{NAME} placeholders in header values using the credential store.
     * Package-private for testing.
     */
    Map<String, String> resolveHeadersForUser(Map<String, String> headers, String userId) {
        Map<String, String> resolved = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            String value = entry.getValue();
            Matcher m = PLACEHOLDER.matcher(value);
            StringBuilder sb = new StringBuilder();
            while (m.find()) {
                String credName = m.group(1);
                String credValue = resolutionService.resolve(userId, credName);
                m.appendReplacement(sb, Matcher.quoteReplacement(credValue != null ? credValue : ""));
            }
            m.appendTail(sb);
            resolved.put(entry.getKey(), sb.toString());
        }
        return resolved;
    }

    /**
     * Extract the userId from the current {@link TaskContext} by reading
     * {@code __agentspan_ctx__} from the task's input data.
     */
    @SuppressWarnings("unchecked")
    private String extractUserIdFromTaskContext() {
        TaskContext ctx = TaskContext.get();
        if (ctx == null) {
            log.debug("No TaskContext available for MCP credential resolution");
            return null;
        }

        Task task = ctx.getTask();
        if (task == null) return null;

        Map<String, Object> inputData = task.getInputData();
        if (inputData == null) return null;

        Object agentCtx = inputData.get("__agentspan_ctx__");
        return extractUserId(agentCtx);
    }

    private String extractUserId(Object ctx) {
        String token = null;
        if (ctx instanceof Map<?, ?> ctxMap) {
            token = (String) ctxMap.get("execution_token");
        } else if (ctx instanceof String s) {
            token = s;
        }
        if (token == null) return null;
        try {
            return tokenService.validate(token).userId();
        } catch (Exception e) {
            log.warn("Failed to validate token for MCP header resolution: {}", e.getMessage());
            return null;
        }
    }

    private boolean containsPlaceholders(Map<String, String> headers) {
        for (String v : headers.values()) {
            if (v != null && PLACEHOLDER.matcher(v).find()) return true;
        }
        return false;
    }
}
