// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.execution;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;
import java.util.UUID;

/**
 * Runs code in a Jupyter kernel over the Jupyter REST API.
 *
 * <p>Requires a running Jupyter server. The kernel is created on first use and reused across calls.
 *
 * <pre>{@code
 * JupyterCodeExecutor executor = new JupyterCodeExecutor("http://localhost:8888", "python3", 30);
 * ExecutionResult result = executor.execute("x = 42; print(x)");
 * }</pre>
 */
public class JupyterCodeExecutor extends CodeExecutor {

    private final String serverUrl;
    private final String kernelName;
    private final String token;
    private final HttpClient httpClient;
    private String kernelId;

    public JupyterCodeExecutor(String serverUrl) {
        this(serverUrl, "python3", 30, null);
    }

    public JupyterCodeExecutor(String serverUrl, String kernelName, int timeout) {
        this(serverUrl, kernelName, timeout, null);
    }

    public JupyterCodeExecutor(String serverUrl, String kernelName, int timeout, String token) {
        super("python", timeout, null);
        this.serverUrl = serverUrl.replaceAll("/$", "");
        this.kernelName = kernelName != null ? kernelName : "python3";
        this.token = token;
        this.httpClient = HttpClient.newHttpClient();
    }

    @Override
    public ExecutionResult execute(String code) {
        try {
            if (kernelId == null) {
                kernelId = createKernel();
            }
            return executeOnKernel(code);
        } catch (Exception e) {
            return new ExecutionResult("", "Jupyter execution error: " + e.getMessage(), 1, false);
        }
    }

    private String createKernel() throws IOException, InterruptedException {
        String body = "{\"name\": \"" + kernelName + "\"}";
        HttpRequest request = buildRequest("POST", "/api/kernels", body);
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 201) {
            throw new IOException("Failed to create Jupyter kernel: HTTP " + response.statusCode());
        }
        String responseBody = response.body();
        int idStart = responseBody.indexOf("\"id\":\"") + 6;
        int idEnd = responseBody.indexOf("\"", idStart);
        return responseBody.substring(idStart, idEnd);
    }

    private ExecutionResult executeOnKernel(String code) throws IOException, InterruptedException {
        String msgId = UUID.randomUUID().toString();
        String encodedCode = Base64.getEncoder().encodeToString(code.getBytes(StandardCharsets.UTF_8));
        String body = "{\"code\": \"" + code.replace("\"", "\\\"").replace("\n", "\\n") + "\", \"silent\": false}";

        HttpRequest request = buildRequest("POST",
            "/api/kernels/" + kernelId + "/execute", body);
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() >= 400) {
            return new ExecutionResult("", "Jupyter kernel error: HTTP " + response.statusCode(), 1, false);
        }
        String responseBody = response.body();
        String output = extractJsonField(responseBody, "text");
        String error = extractJsonField(responseBody, "traceback");
        int exitCode = error.isEmpty() ? 0 : 1;
        return new ExecutionResult(output, error, exitCode, false);
    }

    private HttpRequest buildRequest(String method, String path, String body) {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
            .uri(URI.create(serverUrl + path))
            .header("Content-Type", "application/json");
        if (token != null && !token.isEmpty()) {
            builder.header("Authorization", "Token " + token);
        }
        if ("POST".equals(method)) {
            builder.POST(HttpRequest.BodyPublishers.ofString(body));
        } else {
            builder.GET();
        }
        return builder.build();
    }

    private static String extractJsonField(String json, String field) {
        String key = "\"" + field + "\":\"";
        int start = json.indexOf(key);
        if (start < 0) return "";
        start += key.length();
        int end = json.indexOf("\"", start);
        if (end < 0) return "";
        return json.substring(start, end).replace("\\n", "\n");
    }
}
