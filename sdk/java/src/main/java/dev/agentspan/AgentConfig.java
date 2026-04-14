// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan;

/**
 * Configuration for the Agentspan SDK.
 *
 * <p>Use {@link #fromEnv()} to load configuration from environment variables,
 * or construct directly with explicit values.
 *
 * <p>Environment variables:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL} — server URL (default: http://localhost:6767/api)</li>
 *   <li>{@code AGENTSPAN_AUTH_KEY} — authentication key</li>
 *   <li>{@code AGENTSPAN_AUTH_SECRET} — authentication secret</li>
 *   <li>{@code AGENTSPAN_WORKER_POLL_MS} — worker poll interval in ms (default: 100)</li>
 *   <li>{@code AGENTSPAN_WORKER_THREADS} — worker thread count (default: 5)</li>
 * </ul>
 */
public class AgentConfig {
    private final String serverUrl;
    private final String authKey;
    private final String authSecret;
    private final int workerPollIntervalMs;
    private final int workerThreadCount;

    /**
     * Create an AgentConfig with explicit values.
     *
     * @param serverUrl          the Agentspan server URL
     * @param authKey            authentication key (may be null)
     * @param authSecret         authentication secret (may be null)
     * @param workerPollIntervalMs worker poll interval in milliseconds
     * @param workerThreadCount  number of worker threads
     */
    public AgentConfig(
            String serverUrl,
            String authKey,
            String authSecret,
            int workerPollIntervalMs,
            int workerThreadCount) {
        this.serverUrl = serverUrl != null ? serverUrl : "http://localhost:6767/api";
        this.authKey = authKey;
        this.authSecret = authSecret;
        this.workerPollIntervalMs = workerPollIntervalMs > 0 ? workerPollIntervalMs : 100;
        this.workerThreadCount = workerThreadCount > 0 ? workerThreadCount : 5;
    }

    /**
     * Load configuration from environment variables with sensible defaults.
     *
     * @return a new AgentConfig
     */
    public static AgentConfig fromEnv() {
        return new AgentConfig(
            env("AGENTSPAN_SERVER_URL", "http://localhost:6767/api"),
            env("AGENTSPAN_AUTH_KEY", null),
            env("AGENTSPAN_AUTH_SECRET", null),
            Integer.parseInt(env("AGENTSPAN_WORKER_POLL_MS", "100")),
            Integer.parseInt(env("AGENTSPAN_WORKER_THREADS", "5"))
        );
    }

    private static String env(String key, String defaultValue) {
        String val = System.getenv(key);
        return val != null ? val : defaultValue;
    }

    public String getServerUrl() { return serverUrl; }
    public String getAuthKey() { return authKey; }
    public String getAuthSecret() { return authSecret; }
    public int getWorkerPollIntervalMs() { return workerPollIntervalMs; }
    public int getWorkerThreadCount() { return workerThreadCount; }

    @Override
    public String toString() {
        return "AgentConfig{serverUrl=" + serverUrl + ", workerPollIntervalMs=" + workerPollIntervalMs
                + ", workerThreadCount=" + workerThreadCount + "}";
    }
}
