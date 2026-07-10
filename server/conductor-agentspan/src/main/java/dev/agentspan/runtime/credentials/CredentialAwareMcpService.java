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
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import io.modelcontextprotocol.spec.McpSchema;
import okhttp3.OkHttpClient;

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
 * <p>Placeholders resolve via {@link CredentialResolutionService} against the global
 * credential store.</p>
 */
@Component
@Primary
@ConditionalOnProperty(name = "agentspan.embedded", havingValue = "false", matchIfMissing = true)
public class CredentialAwareMcpService extends MCPService {

    private static final Logger log = LoggerFactory.getLogger(CredentialAwareMcpService.class);
    private static final Pattern PLACEHOLDER = Pattern.compile("#\\{([\\w.]+)}");
    private final CredentialResolutionService resolutionService;

    public CredentialAwareMcpService(
            OkHttpClient conductorAiHttpClient, CredentialResolutionService resolutionService) {
        super(conductorAiHttpClient);
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
     * placeholders are found.
     */
    private Map<String, String> resolveHeaders(Map<String, String> headers) {
        if (headers == null || headers.isEmpty() || !containsPlaceholders(headers)) {
            return headers;
        }
        return resolveHeadersForUser(headers);
    }

    /**
     * Resolve #{NAME} placeholders in header values using the credential store.
     * Package-private for testing.
     */
    Map<String, String> resolveHeadersForUser(Map<String, String> headers) {
        Map<String, String> resolved = new LinkedHashMap<>();
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
            resolved.put(entry.getKey(), sb.toString());
        }
        return resolved;
    }

    private boolean containsPlaceholders(Map<String, String> headers) {
        for (String v : headers.values()) {
            if (v != null && PLACEHOLDER.matcher(v).find()) return true;
        }
        return false;
    }
}
