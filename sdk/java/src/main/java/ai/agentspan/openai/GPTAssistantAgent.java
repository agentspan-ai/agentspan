// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.openai;

import ai.agentspan.Agent;
import ai.agentspan.model.ToolDef;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

/**
 * An agent backed by the OpenAI Assistants API.
 *
 * <p>Wraps an OpenAI Assistant (with its own instructions, tools, and file search
 * capabilities) as an Agentspan Agent. The assistant's execution is handled via the
 * Assistants API Threads and Runs.
 *
 * <pre>{@code
 * // Use an existing assistant
 * Agent agent = GPTAssistantAgent.create("coder")
 *     .assistantId("asst_abc123")
 *     .build();
 *
 * // Or create one on the fly
 * Agent agent = GPTAssistantAgent.create("analyst")
 *     .model("gpt-4o")
 *     .instructions("You are a data analyst.")
 *     .openaiTool("code_interpreter")
 *     .build();
 * }</pre>
 */
public class GPTAssistantAgent {

    private GPTAssistantAgent() {}

    /** Start building a GPTAssistantAgent-backed Agent. */
    public static Builder create(String name) {
        return new Builder(name);
    }

    public static class Builder {
        private final String name;
        private String assistantId;
        private String model = "openai/gpt-4o";
        private String instructions;
        private final List<Map<String, Object>> openaiTools = new ArrayList<>();
        private String apiKey;
        private final List<ToolDef> extraTools = new ArrayList<>();

        private Builder(String name) {
            this.name = name;
        }

        public Builder assistantId(String assistantId) { this.assistantId = assistantId; return this; }
        public Builder model(String model) { this.model = model; return this; }
        public Builder instructions(String instructions) { this.instructions = instructions; return this; }
        public Builder apiKey(String apiKey) { this.apiKey = apiKey; return this; }

        public Builder openaiTool(String type) {
            this.openaiTools.add(Map.of("type", type));
            return this;
        }
        public Builder openaiTool(Map<String, Object> tool) {
            this.openaiTools.add(new LinkedHashMap<>(tool));
            return this;
        }
        public Builder tool(ToolDef tool) { this.extraTools.add(tool); return this; }

        public Agent build() {
            String resolvedModel = model != null && !model.contains("/") ? "openai/" + model : model;
            String resolvedInstructions = instructions != null ? instructions : "You are a helpful assistant.";

            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("_agent_type", "gpt_assistant");
            if (assistantId != null) {
                metadata.put("_assistant_id", assistantId);
            }

            // Captured references for the lambda
            final String capturedAssistantId = assistantId;
            final String capturedModel = resolvedModel;
            final String capturedInstructions = resolvedInstructions;
            final List<Map<String, Object>> capturedTools = new ArrayList<>(openaiTools);
            final String capturedApiKey = apiKey;
            final String agentName = name;
            final AtomicReference<String> assistantIdRef = new AtomicReference<>(capturedAssistantId);

            ToolDef callTool = ToolDef.builder()
                .name(agentName + "_assistant_call")
                .description("Send a message to the OpenAI Assistant and get a response.")
                .inputSchema(Map.of(
                    "type", "object",
                    "properties", Map.of(
                        "message", Map.of("type", "string", "description", "The message to send")
                    ),
                    "required", List.of("message")
                ))
                .func(input -> {
                    String message = input.get("message") instanceof String
                        ? (String) input.get("message") : String.valueOf(input);
                    return runAssistant(message, assistantIdRef, capturedModel,
                        capturedInstructions, capturedTools, capturedApiKey);
                })
                .build();

            List<ToolDef> allTools = new ArrayList<>();
            allTools.add(callTool);
            allTools.addAll(extraTools);

            return Agent.builder()
                .name(name)
                .model(resolvedModel)
                .instructions(resolvedInstructions)
                .tools(allTools)
                .metadata(metadata)
                .maxTurns(1)
                .build();
        }
    }

    @SuppressWarnings("unchecked")
    private static String runAssistant(String message, AtomicReference<String> assistantIdRef,
            String model, String instructions, List<Map<String, Object>> openaiTools, String apiKey) {
        try {
            String key = apiKey != null ? apiKey : System.getenv("OPENAI_API_KEY");
            if (key == null || key.isEmpty()) {
                return "Error: No OpenAI API key provided. Set OPENAI_API_KEY environment variable.";
            }

            HttpClient client = HttpClient.newHttpClient();

            String effectiveAssistantId = assistantIdRef.get();
            if (effectiveAssistantId == null) {
                Map<String, Object> createBody = new LinkedHashMap<>();
                String modelName = model != null ? model.replace("openai/", "") : "gpt-4o";
                createBody.put("model", modelName);
                createBody.put("instructions", instructions);
                if (!openaiTools.isEmpty()) createBody.put("tools", openaiTools);
                Map<String, Object> assistantResp = apiPost(client, key, "/assistants", createBody);
                effectiveAssistantId = (String) assistantResp.get("id");
                assistantIdRef.set(effectiveAssistantId);
            }

            // Create thread
            Map<String, Object> threadResp = apiPost(client, key, "/threads", Map.of());
            String threadId = (String) threadResp.get("id");

            // Add message
            Map<String, Object> msgBody = new LinkedHashMap<>();
            msgBody.put("role", "user");
            msgBody.put("content", message);
            apiPost(client, key, "/threads/" + threadId + "/messages", msgBody);

            // Create run
            Map<String, Object> runBody = new LinkedHashMap<>();
            runBody.put("assistant_id", effectiveAssistantId);
            Map<String, Object> runResp = apiPost(client, key, "/threads/" + threadId + "/runs", runBody);
            String runId = (String) runResp.get("id");

            // Poll until complete
            for (int i = 0; i < 60; i++) {
                Thread.sleep(1000);
                Map<String, Object> statusResp = apiGet(client, key, "/threads/" + threadId + "/runs/" + runId);
                String status = (String) statusResp.get("status");
                if ("completed".equals(status)) {
                    Map<String, Object> msgs = apiGet(client, key, "/threads/" + threadId + "/messages");
                    List<Map<String, Object>> data = (List<Map<String, Object>>) msgs.get("data");
                    if (data != null) {
                        for (Map<String, Object> msg : data) {
                            if ("assistant".equals(msg.get("role"))) {
                                List<Map<String, Object>> content = (List<Map<String, Object>>) msg.get("content");
                                if (content != null) {
                                    StringBuilder sb = new StringBuilder();
                                    for (Map<String, Object> block : content) {
                                        if ("text".equals(block.get("type"))) {
                                            Map<String, Object> textObj = (Map<String, Object>) block.get("text");
                                            if (textObj != null) sb.append(textObj.get("value"));
                                        }
                                    }
                                    if (sb.length() > 0) return sb.toString();
                                }
                            }
                        }
                    }
                    return "No response from assistant.";
                } else if ("failed".equals(status) || "cancelled".equals(status) || "expired".equals(status)) {
                    return "Assistant run ended with status: " + status;
                }
            }
            return "Assistant run timed out.";
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return "OpenAI Assistant interrupted.";
        } catch (Exception e) {
            return "OpenAI Assistant error: " + e.getMessage();
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> apiPost(HttpClient client, String apiKey,
            String path, Object body) throws Exception {
        String json = ai.agentspan.internal.JsonMapper.toJson(body);
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.openai.com/v1" + path))
            .header("Authorization", "Bearer " + apiKey)
            .header("Content-Type", "application/json")
            .header("OpenAI-Beta", "assistants=v2")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();
        HttpResponse<String> resp = client.send(request, HttpResponse.BodyHandlers.ofString());
        return ai.agentspan.internal.JsonMapper.fromJson(resp.body(), Map.class);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> apiGet(HttpClient client, String apiKey,
            String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.openai.com/v1" + path))
            .header("Authorization", "Bearer " + apiKey)
            .header("OpenAI-Beta", "assistants=v2")
            .GET()
            .build();
        HttpResponse<String> resp = client.send(request, HttpResponse.BodyHandlers.ofString());
        return ai.agentspan.internal.JsonMapper.fromJson(resp.body(), Map.class);
    }
}
