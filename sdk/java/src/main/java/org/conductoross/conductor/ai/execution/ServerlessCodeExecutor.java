// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.execution;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import org.conductoross.conductor.ai.internal.JsonMapper;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Execute code via a remote serverless execution service.
 *
 * <p>Mirrors Python's {@code ServerlessCodeExecutor}: an extensible base for
 * services such as AWS Lambda, Cloud Functions, or any hosted code-execution
 * API. POSTs a JSON body {@code {code, language, timeout}} to the configured
 * {@code endpoint} and maps the JSON response
 * ({@code output}/{@code stdout}, {@code error}/{@code stderr},
 * {@code exit_code}) to an {@link ExecutionResult}.
 *
 * <p>Configuration mirrors the Python config: {@code endpoint}, optional
 * {@code apiKey} (sent as a Bearer token), {@code timeout}, and extra
 * {@code headers}. It never throws — an unreachable endpoint or a transport
 * error is returned as a structured {@link ExecutionResult}. Subclass and
 * override {@link #sendRequest(String)} to integrate with a specific service.
 *
 * <pre>{@code
 * ServerlessCodeExecutor exec = new ServerlessCodeExecutor(
 *         "https://api.myservice.com/execute", "sk-...", "python", 30, null);
 * ExecutionResult result = exec.execute("print('hello from the cloud')");
 * }</pre>
 */
public class ServerlessCodeExecutor extends CodeExecutor {

    private final String endpoint;
    private final String apiKey;
    private final Map<String, String> headers;

    public ServerlessCodeExecutor(String endpoint) {
        this(endpoint, null, "python", 30, null);
    }

    public ServerlessCodeExecutor(
            String endpoint, String apiKey, String language, int timeout, Map<String, String> headers) {
        super(language, timeout, null);
        this.endpoint = endpoint;
        this.apiKey = apiKey;
        this.headers = headers != null ? new LinkedHashMap<>(headers) : new LinkedHashMap<>();
    }

    public String getEndpoint() {
        return endpoint;
    }

    public Map<String, String> getHeaders() {
        return headers;
    }

    @Override
    public ExecutionResult execute(String code) {
        if (code == null || code.isEmpty()) {
            return new ExecutionResult("No code provided. Nothing to execute.", "", 0, false);
        }
        return sendRequest(code);
    }

    /**
     * Send code to the remote execution service. Override to integrate with a
     * specific service; the default uses the JDK HTTP client.
     */
    protected ExecutionResult sendRequest(String code) {
        try {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("code", code);
            payload.put("language", language);
            payload.put("timeout", timeout);

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(Math.max(1, timeout)))
                    .build();

            HttpRequest.Builder builder = HttpRequest.newBuilder()
                    .uri(URI.create(endpoint))
                    .timeout(Duration.ofSeconds(Math.max(1, timeout) + 5))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(JsonMapper.toJson(payload)));
            if (apiKey != null && !apiKey.isEmpty()) {
                builder.header("Authorization", "Bearer " + apiKey);
            }
            for (Map.Entry<String, String> h : headers.entrySet()) {
                builder.header(h.getKey(), h.getValue());
            }

            HttpResponse<String> resp = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() >= 400) {
                return new ExecutionResult(
                        "", "Request failed: HTTP " + resp.statusCode() + ": " + resp.body(), 1, false);
            }
            return parseResponse(resp.body());

        } catch (java.net.http.HttpTimeoutException e) {
            return new ExecutionResult("", "Execution timed out after " + timeout + "s", -1, true);
        } catch (Exception e) {
            String msg = e.getMessage() != null ? e.getMessage() : e.toString();
            return new ExecutionResult("", "Request failed: " + msg, 1, false);
        }
    }

    private static ExecutionResult parseResponse(String bodyJson) {
        try {
            JsonNode node = JsonMapper.get().readTree(bodyJson);
            String output = firstText(node, "output", "stdout");
            String error = firstText(node, "error", "stderr");
            int exitCode = node.has("exit_code") ? node.get("exit_code").asInt(0) : 0;
            return new ExecutionResult(output, error, exitCode, false);
        } catch (Exception e) {
            return new ExecutionResult(bodyJson, "", 0, false);
        }
    }

    private static String firstText(JsonNode node, String... keys) {
        for (String k : keys) {
            JsonNode v = node.get(k);
            if (v != null && !v.isNull()) {
                return v.isTextual() ? v.asText() : v.toString();
            }
        }
        return "";
    }
}
