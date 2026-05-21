// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agent;
import ai.agentspan.frameworks.LangChain4jAgent;

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
     * Convert a name + native ChatModel + system prompt + {@code @Tool}
     * POJOs into an Agentspan {@link Agent}.
     */
    public static Agent toAgentspan(String name, ChatModel model, String systemPrompt, Object... tools) {
        String modelString = providerSlashModel(model);
        return LangChain4jAgent.from(name, modelString, systemPrompt, tools);
    }

    /** Same as {@link #toAgentspan(String, ChatModel, String, Object...)} with no tools. */
    public static Agent toAgentspan(String name, ChatModel model, String systemPrompt) {
        String modelString = providerSlashModel(model);
        return LangChain4jAgent.from(name, modelString, systemPrompt);
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
