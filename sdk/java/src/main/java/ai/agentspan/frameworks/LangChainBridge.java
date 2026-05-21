// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.frameworks;

import ai.agentspan.Agent;

import dev.langchain4j.model.ModelProvider;
import dev.langchain4j.model.chat.ChatModel;

/**
 * Adapter that takes native LangChain4j components (a {@link ChatModel} and
 * {@code @Tool}-annotated POJOs) and produces an Agentspan {@link Agent}.
 *
 * <p>The model object is used only to extract the {@code provider/model} string
 * that the Agentspan server needs — Agentspan owns the LLM call and the
 * credentials live on the server, so the client never invokes the local
 * {@link ChatModel} directly.
 *
 * <p>The tool POJOs carry the canonical {@code @dev.langchain4j.agent.tool.Tool}
 * annotation; {@link LangChain4jAgent#from} extracts them via reflection.
 */
public final class LangChainBridge {

    private LangChainBridge() {}

    /**
     * Build an Agentspan {@link Agent.Builder} from a native LangChain4j
     * {@link ChatModel} and {@code @Tool}-annotated POJOs. Returning the
     * Builder lets callers attach Agentspan-only features (guardrails,
     * gate, termination, callbacks) before {@code .build()}:
     *
     * <pre>{@code
     * Agent agent = LangChainBridge.agentBuilder("name", model, "prompt", new MyTools())
     *     .guardrails(piiGuard)
     *     .build();
     * Agentspan.run(agent, "...");
     * }</pre>
     *
     * <p>For the simple no-decoration case, prefer the direct drop-in:
     * {@code Agentspan.run(model, prompt, tools)}.
     */
    public static Agent.Builder agentBuilder(String name, ChatModel model, String systemPrompt, Object... tools) {
        String modelString = providerSlashModel(model);
        // Mirrors LangChain4jAgent.from but returns the Builder so callers can
        // decorate. Imports are kept package-local since LangChain4jAgent is
        // an ai.agentspan.frameworks class.
        java.util.List<ai.agentspan.model.ToolDef> toolDefs =
                LangChain4jAgent.extractTools(tools);
        Agent.Builder b = Agent.builder()
                .name(name)
                .model(modelString)
                .instructions(systemPrompt);
        if (!toolDefs.isEmpty()) {
            b.tools(toolDefs);
        }
        return b;
    }

    /**
     * Map a LangChain4j {@link ChatModel} to the {@code provider/model} string
     * format expected by the Agentspan server (e.g. {@code openai/gpt-4o-mini}).
     *
     * <p>The provider id is read from {@link ChatModel#provider()} and the model
     * name from {@code defaultRequestParameters().modelName()}; both are part of
     * the public LangChain4j SDK.
     */
    public static String providerSlashModel(ChatModel model) {
        String modelName = null;
        try {
            modelName = model.defaultRequestParameters().modelName();
        } catch (Throwable ignored) {}

        if (modelName == null || modelName.isEmpty()) {
            throw new IllegalArgumentException(
                "Could not read model name from ChatModel " + model.getClass().getName());
        }

        // If the user already provided a slash-format string, accept it.
        if (modelName.contains("/")) return modelName;

        String provider = mapProvider(safeProvider(model));
        return provider + "/" + modelName;
    }

    private static ModelProvider safeProvider(ChatModel model) {
        try {
            return model.provider();
        } catch (Throwable t) {
            return ModelProvider.OTHER;
        }
    }

    private static String mapProvider(ModelProvider p) {
        if (p == null) return "openai";
        return switch (p) {
            case OPEN_AI -> "openai";
            case ANTHROPIC -> "anthropic";
            case GOOGLE_AI_GEMINI -> "google_gemini";
            case AMAZON_BEDROCK -> "bedrock";
            case MISTRAL_AI -> "mistralai";
            case OLLAMA -> "ollama";
            case AZURE_OPEN_AI -> "openai";
            case GOOGLE_VERTEX_AI_GEMINI -> "google_gemini";
            default -> "openai";
        };
    }
}
