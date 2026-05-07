// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.tools;

import ai.agentspan.model.ToolDef;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Factory for tools generated from an OpenAPI spec, Swagger spec, Postman collection, or base URL.
 *
 * <p>The server auto-detects the format at compile time and expands the spec into individual
 * HTTP tools. No worker process is needed.
 *
 * <pre>{@code
 * ToolDef stripe = ApiTool.from("https://api.stripe.com/openapi.json")
 *     .header("Authorization", "Bearer ${STRIPE_KEY}")
 *     .credentials("STRIPE_KEY")
 *     .maxTools(20)
 *     .build();
 * }</pre>
 */
public class ApiTool {

    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{(\\w+)}");

    private ApiTool() {}

    public static Builder from(String url) {
        return new Builder(url);
    }

    public static class Builder {
        private final String url;
        private String name;
        private String description;
        private final Map<String, String> headers = new LinkedHashMap<>();
        private List<String> toolNames;
        private int maxTools = 64;
        private final List<String> credentials = new ArrayList<>();

        private Builder(String url) {
            this.url = url;
        }

        public Builder name(String name) {
            this.name = name;
            return this;
        }

        public Builder description(String description) {
            this.description = description;
            return this;
        }

        public Builder header(String key, String value) {
            this.headers.put(key, value);
            return this;
        }

        public Builder headers(Map<String, String> headers) {
            this.headers.putAll(headers);
            return this;
        }

        public Builder toolNames(List<String> toolNames) {
            this.toolNames = new ArrayList<>(toolNames);
            return this;
        }

        public Builder toolNames(String... toolNames) {
            this.toolNames = Arrays.asList(toolNames);
            return this;
        }

        public Builder maxTools(int maxTools) {
            this.maxTools = maxTools;
            return this;
        }

        public Builder credentials(List<String> credentials) {
            this.credentials.addAll(credentials);
            return this;
        }

        public Builder credentials(String... credentials) {
            this.credentials.addAll(Arrays.asList(credentials));
            return this;
        }

        public ToolDef build() {
            // Validate: any ${NAME} in headers must be in credentials
            if (!headers.isEmpty()) {
                for (String value : headers.values()) {
                    Matcher m = PLACEHOLDER.matcher(value);
                    while (m.find()) {
                        String placeholder = m.group(1);
                        if (!credentials.contains(placeholder)) {
                            throw new IllegalArgumentException(
                                "Header placeholder '${" + placeholder + "}' not declared in credentials. "
                                + "Add '" + placeholder + "' to the credentials list.");
                        }
                    }
                }
            }

            Map<String, Object> config = new LinkedHashMap<>();
            config.put("url", url);
            if (!headers.isEmpty()) config.put("headers", headers);
            if (toolNames != null) config.put("tool_names", toolNames);
            config.put("max_tools", maxTools);

            return ToolDef.builder()
                    .name(name != null ? name : "api_tools")
                    .description(description != null ? description : "API tools from " + url)
                    .toolType("api")
                    .config(config)
                    .credentials(credentials)
                    .build();
        }
    }
}
