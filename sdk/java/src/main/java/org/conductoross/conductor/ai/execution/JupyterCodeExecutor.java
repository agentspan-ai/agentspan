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
 * Execute code against a Jupyter Kernel Gateway.
 *
 * <p>Mirrors Python's {@code JupyterCodeExecutor}, ported to the gateway's HTTP
 * surface (Java has no in-process {@code jupyter_client}). Configuration mirrors
 * the Python config: the gateway {@code url}, the {@code kernel} name, and a
 * {@code timeout}.
 *
 * <p>Execution starts (or reuses) a kernel via {@code POST {url}/api/kernels},
 * then submits the snippet to the gateway's REST execute endpoint
 * ({@code POST {url}/api/kernels/{id}/execute}, as exposed by
 * {@code jupyter-kernel-gateway}'s {@code notebook-http} / REST modes). It never
 * throws — an unreachable gateway, a missing dependency, or an error cell is
 * returned as a structured {@link ExecutionResult}.
 *
 * <pre>{@code
 * JupyterCodeExecutor exec = new JupyterCodeExecutor("http://localhost:8888/", "python3", 30);
 * ExecutionResult result = exec.execute("print(40 + 2)");
 * }</pre>
 */
public class JupyterCodeExecutor extends CodeExecutor {

    private final String url;
    private final String kernelName;
    private String kernelId;

    public JupyterCodeExecutor(String url) {
        this(url, "python3", 30);
    }

    public JupyterCodeExecutor(String url, String kernelName, int timeout) {
        super("python", timeout, null);
        this.url = stripTrailingSlash(url);
        this.kernelName = kernelName != null ? kernelName : "python3";
    }

    public String getUrl() {
        return url;
    }

    public String getKernelName() {
        return kernelName;
    }

    @Override
    public ExecutionResult execute(String code) {
        if (code == null || code.isEmpty()) {
            return new ExecutionResult("No code provided. Nothing to execute.", "", 0, false);
        }
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(Math.max(1, timeout)))
                    .build();

            if (kernelId == null) {
                kernelId = startKernel(client);
            }

            Map<String, Object> body = new LinkedHashMap<>();
            body.put("code", code);
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url + "/api/kernels/" + kernelId + "/execute"))
                    .timeout(Duration.ofSeconds(Math.max(1, timeout)))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(JsonMapper.toJson(body)))
                    .build();

            HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() >= 400) {
                return new ExecutionResult(
                        "", "Jupyter gateway returned HTTP " + resp.statusCode() + ": " + resp.body(), 1, false);
            }
            return parseExecuteResponse(resp.body());

        } catch (java.net.http.HttpTimeoutException e) {
            return new ExecutionResult("", "Execution timed out after " + timeout + "s", -1, true);
        } catch (Exception e) {
            String msg = e.getMessage() != null ? e.getMessage() : e.toString();
            return new ExecutionResult("", "Kernel/gateway request failed: " + msg, 1, false);
        }
    }

    /** Create a kernel via the gateway and return its id. */
    private String startKernel(HttpClient client) throws Exception {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("name", kernelName);
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(url + "/api/kernels"))
                .timeout(Duration.ofSeconds(Math.max(1, timeout)))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(JsonMapper.toJson(body)))
                .build();
        HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
        if (resp.statusCode() >= 400) {
            throw new IllegalStateException(
                    "kernel start returned HTTP " + resp.statusCode() + ": " + resp.body());
        }
        JsonNode node = JsonMapper.get().readTree(resp.body());
        JsonNode id = node.get("id");
        if (id == null || id.isNull()) {
            throw new IllegalStateException("kernel start response missing 'id': " + resp.body());
        }
        return id.asText();
    }

    /**
     * Parse the gateway's execute response. Accepts the common shapes:
     * {@code {output, error, exit_code}}, {@code {stdout, stderr}}, or
     * {@code {status, ...}}.
     */
    private static ExecutionResult parseExecuteResponse(String bodyJson) {
        try {
            JsonNode node = JsonMapper.get().readTree(bodyJson);
            String output = firstText(node, "output", "stdout");
            String error = firstText(node, "error", "stderr");
            int exitCode;
            if (node.has("exit_code")) {
                exitCode = node.get("exit_code").asInt(0);
            } else {
                exitCode = (error != null && !error.isEmpty()) ? 1 : 0;
            }
            return new ExecutionResult(output, error, exitCode, false);
        } catch (Exception e) {
            // Body wasn't JSON — treat the raw text as stdout.
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

    private static String stripTrailingSlash(String s) {
        if (s == null) return "";
        return s.endsWith("/") ? s.substring(0, s.length() - 1) : s;
    }
}
