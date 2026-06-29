// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.tools;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.conductoross.conductor.ai.model.ToolDef;

/**
 * Builder for API server-side tools created from an OpenAPI/Swagger spec,
 * Postman collection, or base URL.
 *
 * <p>At compile time the Conductor server discovers API operations from the spec
 * and expands them into individual tools. Tool calls execute as standard
 * Conductor {@code HTTP} tasks — no worker process is needed.
 *
 * <p>Serialized as {@code toolType: "api"} with config keys {@code url},
 * {@code headers}, {@code tool_names}, and {@code max_tools} (default 64),
 * matching the Python SDK {@code api_tool} and C# {@code ApiTools.Create}.
 *
 * <p>Headers can reference credentials using {@code ${NAME}} syntax. The server
 * resolves these at execution time from the credential store. Any {@code ${NAME}}
 * placeholder used in headers must be declared via {@link Builder#credentials}.
 *
 * <pre>{@code
 * ToolDef stripe = ApiTool.builder()
 *     .url("https://api.stripe.com/openapi.json")
 *     .header("Authorization", "Bearer ${STRIPE_KEY}")
 *     .credentials("STRIPE_KEY")
 *     .maxTools(20)
 *     .build();
 * }</pre>
 */
public class ApiTool {

    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{(\\w+)}");

    private ApiTool() {}

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private String url;
        private String name;
        private String description;
        private Map<String, String> headers = new LinkedHashMap<>();
        private List<String> toolNames;
        private int maxTools = 64;
        private List<String> credentials = new ArrayList<>();

        /** URL to the spec, collection, or base URL for auto-discovery (required). */
        public Builder url(String url) {
            this.url = url;
            return this;
        }

        /** Optional override name (defaults to {@code "api_tools"}). */
        public Builder name(String name) {
            this.name = name;
            return this;
        }

        /** Optional override description. */
        public Builder description(String description) {
            this.description = description;
            return this;
        }

        /** Add a single global header. Use {@code ${NAME}} for credential placeholders. */
        public Builder header(String key, String value) {
            this.headers.put(key, value);
            return this;
        }

        public Builder headers(Map<String, String> headers) {
            this.headers = new LinkedHashMap<>(headers);
            return this;
        }

        /** Optional whitelist — only include these operation IDs. */
        public Builder toolNames(String... toolNames) {
            this.toolNames = new ArrayList<>(List.of(toolNames));
            return this;
        }

        /** Optional whitelist — only include these operation IDs. */
        public Builder toolNames(List<String> toolNames) {
            this.toolNames = new ArrayList<>(toolNames);
            return this;
        }

        /**
         * If operations exceed this, a filter LLM selects the most relevant ones
         * based on the user's prompt (default 64).
         */
        public Builder maxTools(int maxTools) {
            this.maxTools = maxTools;
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

        public ToolDef build() {
            if (url == null || url.isEmpty()) {
                throw new IllegalArgumentException("ApiTool requires a URL");
            }

            // Validate: any ${NAME} in headers must be declared in credentials (Python parity).
            if (!headers.isEmpty()) {
                Set<String> placeholders = new HashSet<>();
                Matcher m = PLACEHOLDER.matcher(headers.toString());
                while (m.find()) {
                    placeholders.add(m.group(1));
                }
                Set<String> missing = new HashSet<>(placeholders);
                missing.removeAll(credentials);
                if (!missing.isEmpty()) {
                    throw new IllegalArgumentException("Header placeholder(s) " + missing
                            + " not declared in credentials=" + credentials
                            + ". Add them to the credentials list.");
                }
            }

            Map<String, Object> config = new LinkedHashMap<>();
            config.put("url", url);
            if (!headers.isEmpty()) config.put("headers", headers);
            if (toolNames != null) config.put("tool_names", toolNames);
            config.put("max_tools", maxTools);

            return new ToolDef.Builder()
                    .name(name != null ? name : "api_tools")
                    .description(description != null ? description : "API tools from " + url)
                    .toolType("api")
                    .config(config)
                    .credentials(credentials)
                    .build();
        }
    }
}
