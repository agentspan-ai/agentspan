// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

/**
 * Shared settings for all examples. Reads from environment variables.
 *
 * <p>Set these before running examples:
 * <pre>
 * export AGENTSPAN_SERVER_URL=http://localhost:8080/api
 * export AGENTSPAN_LLM_MODEL=openai/gpt-4o
 * export AGENTSPAN_AUTH_KEY=your-key       # optional
 * export AGENTSPAN_AUTH_SECRET=your-secret # optional
 * </pre>
 */
public class Settings {
    private static final java.util.Map<String, String> ENV = System.getenv();

    public static final String SERVER_URL =
        ENV.getOrDefault("AGENTSPAN_SERVER_URL", "http://localhost:8080/api");

    public static final String LLM_MODEL =
        ENV.getOrDefault("AGENTSPAN_LLM_MODEL", "openai/gpt-4o");

    public static final String AUTH_KEY =
        ENV.get("AGENTSPAN_AUTH_KEY");

    public static final String AUTH_SECRET =
        ENV.get("AGENTSPAN_AUTH_SECRET");

    private Settings() {}
}
