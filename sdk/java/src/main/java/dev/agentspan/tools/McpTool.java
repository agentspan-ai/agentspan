// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.tools;

import dev.agentspan.model.ToolDef;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Builder for MCP (Model Context Protocol) server-side tools.
 *
 * <p>MCP tools connect to MCP servers to provide tools to agents.
 * No local function is needed — the server handles MCP communication.
 *
 * <p>Example:
 * <pre>{@code
 * ToolDef mcpTool = McpTool.builder()
 *     .name("filesystem")
 *     .description("Access the local filesystem via MCP")
 *     .serverUrl("http://localhost:3001")
 *     .toolName("read_file")
 *     .build();
 * }</pre>
 */
public class McpTool {

    private McpTool() {}

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private String name;
        private String description = "";
        private String serverUrl;
        private String toolName;
        private Map<String, String> headers = new HashMap<>();
        private Map<String, Object> inputSchema;
        private List<String> credentials = new ArrayList<>();
        private Map<String, Object> additionalConfig = new HashMap<>();

        public Builder name(String name) { this.name = name; return this; }
        public Builder description(String description) { this.description = description; return this; }
        public Builder serverUrl(String serverUrl) { this.serverUrl = serverUrl; return this; }
        public Builder toolName(String toolName) { this.toolName = toolName; return this; }

        public Builder header(String key, String value) {
            this.headers.put(key, value);
            return this;
        }

        public Builder headers(Map<String, String> headers) {
            this.headers = new HashMap<>(headers);
            return this;
        }

        public Builder inputSchema(Map<String, Object> inputSchema) {
            this.inputSchema = inputSchema;
            return this;
        }

        public Builder credentials(String... credentials) {
            for (String cred : credentials) {
                this.credentials.add(cred);
            }
            return this;
        }

        public Builder credentials(List<String> credentials) {
            this.credentials = new ArrayList<>(credentials);
            return this;
        }

        public Builder config(String key, Object value) {
            this.additionalConfig.put(key, value);
            return this;
        }

        public ToolDef build() {
            if (name == null || name.isEmpty()) {
                throw new IllegalArgumentException("McpTool requires a name");
            }

            Map<String, Object> config = new HashMap<>(additionalConfig);
            if (serverUrl != null) config.put("serverUrl", serverUrl);
            if (toolName != null) config.put("toolName", toolName);
            if (!headers.isEmpty()) config.put("headers", headers);

            // Build a basic input schema if not provided
            Map<String, Object> schema = inputSchema;
            if (schema == null) {
                schema = new HashMap<>();
                schema.put("type", "object");
                schema.put("properties", new HashMap<>());
            }

            return new ToolDef.Builder()
                .name(name)
                .description(description)
                .inputSchema(schema)
                .toolType("mcp")
                .config(config)
                .credentials(credentials)
                .build();
        }
    }
}
