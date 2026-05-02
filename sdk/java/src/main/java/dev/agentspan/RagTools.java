// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan;

import dev.agentspan.model.ToolDef;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Factory methods for RAG (Retrieval-Augmented Generation) tools.
 *
 * <p>RAG tools run entirely on the Conductor server — no local worker process
 * is needed. The server handles embedding generation and vector DB operations.
 *
 * <p>Example:
 * <pre>{@code
 * ToolDef search = RagTools.searchTool(
 *     "search_docs", "Search the knowledge base",
 *     "pgvectordb", "product_docs", "openai", "text-embedding-3-small", 5);
 *
 * ToolDef index = RagTools.indexTool(
 *     "index_doc", "Index a document into the knowledge base",
 *     "pgvectordb", "product_docs", "openai", "text-embedding-3-small");
 * }</pre>
 */
public class RagTools {

    private RagTools() {}

    /**
     * Create a vector search tool (Conductor LLM_SEARCH_INDEX task).
     *
     * @param name tool name shown to the LLM
     * @param description tool description shown to the LLM
     * @param vectorDb vector database type (e.g. "pgvectordb", "pineconedb", "mongodb_atlas")
     * @param index collection/index name in the vector database
     * @param embeddingModelProvider embedding provider (e.g. "openai")
     * @param embeddingModel embedding model name (e.g. "text-embedding-3-small")
     * @param maxResults maximum number of results to return
     * @return a ToolDef with toolType "rag_search"
     */
    public static ToolDef searchTool(String name, String description,
            String vectorDb, String index,
            String embeddingModelProvider, String embeddingModel,
            int maxResults) {
        return searchTool(name, description, vectorDb, index,
                embeddingModelProvider, embeddingModel, "default_ns", maxResults);
    }

    /**
     * Create a vector search tool with explicit namespace.
     */
    public static ToolDef searchTool(String name, String description,
            String vectorDb, String index,
            String embeddingModelProvider, String embeddingModel,
            String namespace, int maxResults) {
        Map<String, Object> inputSchema = new LinkedHashMap<>();
        inputSchema.put("type", "object");
        Map<String, Object> props = new LinkedHashMap<>();
        Map<String, Object> queryProp = new LinkedHashMap<>();
        queryProp.put("type", "string");
        queryProp.put("description", "The search query.");
        props.put("query", queryProp);
        inputSchema.put("properties", props);
        inputSchema.put("required", java.util.List.of("query"));

        Map<String, Object> config = new LinkedHashMap<>();
        config.put("taskType", "LLM_SEARCH_INDEX");
        config.put("vectorDB", vectorDb);
        config.put("namespace", namespace);
        config.put("index", index);
        config.put("embeddingModelProvider", embeddingModelProvider);
        config.put("embeddingModel", embeddingModel);
        config.put("maxResults", maxResults);

        return ToolDef.builder()
                .name(name)
                .description(description)
                .inputSchema(inputSchema)
                .toolType("rag_search")
                .config(config)
                .build();
    }

    /**
     * Create a vector index tool (Conductor LLM_INDEX_TEXT task).
     *
     * @param name tool name shown to the LLM
     * @param description tool description shown to the LLM
     * @param vectorDb vector database type (e.g. "pgvectordb")
     * @param index collection/index name in the vector database
     * @param embeddingModelProvider embedding provider (e.g. "openai")
     * @param embeddingModel embedding model name (e.g. "text-embedding-3-small")
     * @return a ToolDef with toolType "rag_index"
     */
    public static ToolDef indexTool(String name, String description,
            String vectorDb, String index,
            String embeddingModelProvider, String embeddingModel) {
        return indexTool(name, description, vectorDb, index,
                embeddingModelProvider, embeddingModel, "default_ns");
    }

    /**
     * Create a vector index tool with explicit namespace.
     */
    public static ToolDef indexTool(String name, String description,
            String vectorDb, String index,
            String embeddingModelProvider, String embeddingModel,
            String namespace) {
        Map<String, Object> inputSchema = new LinkedHashMap<>();
        inputSchema.put("type", "object");
        Map<String, Object> props = new LinkedHashMap<>();
        Map<String, Object> textProp = new LinkedHashMap<>();
        textProp.put("type", "string");
        textProp.put("description", "The text content to index.");
        props.put("text", textProp);
        Map<String, Object> docIdProp = new LinkedHashMap<>();
        docIdProp.put("type", "string");
        docIdProp.put("description", "Unique document identifier.");
        props.put("docId", docIdProp);
        inputSchema.put("properties", props);
        inputSchema.put("required", java.util.List.of("text", "docId"));

        Map<String, Object> config = new LinkedHashMap<>();
        config.put("taskType", "LLM_INDEX_TEXT");
        config.put("vectorDB", vectorDb);
        config.put("namespace", namespace);
        config.put("index", index);
        config.put("embeddingModelProvider", embeddingModelProvider);
        config.put("embeddingModel", embeddingModel);

        return ToolDef.builder()
                .name(name)
                .description(description)
                .inputSchema(inputSchema)
                .toolType("rag_index")
                .config(config)
                .build();
    }
}
