// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 35 — RAG Agent
 *
 * <p>Java port of <code>sdk/python/examples/adk/35_rag_agent.py</code>.
 *
 * <p>Demonstrates: a RAG agent flow with index + search tools. The Python
 * source uses Agentspan's {@code search_tool} / {@code index_tool} factory
 * helpers (mapped to Conductor's LLM_INDEX_TEXT / LLM_SEARCH_INDEX system
 * tasks).
 *
 * <p>Did not port cleanly: no equivalent Java {@code search_tool} /
 * {@code index_tool} factory helpers in this SDK, so the Java port stubs
 * the same tool names + signatures as in-process static functions that record
 * the request and return canned shapes — preserving the example flow.
 */
public class Example35RagAgent {

    // ── Knowledge base content to index (mirrors Python DOCUMENTS) ───────
    public static class Doc {
        public final String docId;
        public final String text;
        Doc(String docId, String text) {
            this.docId = docId;
            this.text = text;
        }
    }

    public static final List<Doc> DOCUMENTS = List.of(
        new Doc("auth-guide",
            "API Authentication Guide. To authenticate API requests, include an "
            + "Authorization header with a Bearer token. Tokens can be generated from "
            + "the Settings > API Keys page in the dashboard. Tokens expire after 30 "
            + "days and must be rotated. Service accounts can use long-lived tokens "
            + "by enabling the 'non-expiring' option. Rate limits are applied per-token: "
            + "1000 requests/minute for standard tokens, 5000 for enterprise tokens."),
        new Doc("workflow-tasks",
            "Workflow Task Types. Conductor supports several task types: SIMPLE tasks "
            + "are executed by workers polling for work. HTTP tasks make REST API calls "
            + "directly from the server. INLINE tasks run JavaScript expressions for "
            + "lightweight data transformations. SUB_WORKFLOW tasks invoke another workflow "
            + "as a child. FORK_JOIN_DYNAMIC tasks execute multiple tasks in parallel. "
            + "SWITCH tasks provide conditional branching based on expressions. WAIT tasks "
            + "pause execution until an external signal is received."),
        new Doc("error-handling",
            "Error Handling and Retries. Tasks support configurable retry policies. "
            + "Set retryCount to the number of retry attempts (default 3). retryLogic can "
            + "be FIXED, EXPONENTIAL_BACKOFF, or LINEAR_BACKOFF. retryDelaySeconds sets "
            + "the base delay between retries. Tasks can be marked as optional: true so "
            + "workflow execution continues even if they fail. Use timeoutSeconds to set "
            + "a maximum execution time. The timeoutPolicy can be RETRY, TIME_OUT_WF, or "
            + "ALERT_ONLY. Failed tasks populate reasonForIncompletion with error details."),
        new Doc("agent-configuration",
            "Agent Configuration. Agents are defined with a name, model, instructions, "
            + "and tools. The model field uses the format 'provider/model_name', e.g. "
            + "'openai/gpt-4o' or 'anthropic/claude-sonnet-4-20250514'. Instructions can be "
            + "a string or a PromptTemplate referencing a stored prompt. Tools can be "
            + "@tool-decorated Python functions, http_tool for REST APIs, mcp_tool for "
            + "MCP servers, or agent_tool to wrap another agent as a callable tool. "
            + "Set max_turns to limit the agent's reasoning loop (default 25)."),
        new Doc("vector-search-setup",
            "Vector Search Setup. To enable RAG capabilities, configure a vector database "
            + "in application-rag.properties. Supported backends: pgvectordb (PostgreSQL with "
            + "pgvector extension), pineconedb (Pinecone cloud), and mongodb_atlas (MongoDB "
            + "Atlas Vector Search). For pgvector, install the extension with "
            + "'CREATE EXTENSION vector' and set the JDBC connection string. Embedding "
            + "dimensions default to 1536 (matching text-embedding-3-small). Supported "
            + "distance metrics: cosine (default), euclidean, and inner_product. HNSW "
            + "indexing is recommended for production workloads."),
        new Doc("multi-agent-patterns",
            "Multi-Agent Patterns. SequentialAgent runs sub-agents in order, passing "
            + "state via output_key. ParallelAgent runs sub-agents concurrently and "
            + "aggregates results. LoopAgent repeats a sub-agent up to max_iterations "
            + "times, useful for iterative refinement. For dynamic routing, use a router "
            + "agent or handoff conditions (OnTextMention, OnToolResult, OnCondition). "
            + "The swarm strategy enables peer-to-peer agent delegation. Use "
            + "allowed_transitions to constrain which agents can hand off to which."),
        new Doc("webhook-events",
            "Webhook and Event Configuration. Conductor supports webhook-based task "
            + "completion via WAIT tasks. Configure event handlers with action types: "
            + "complete_task, fail_task, or update_variables. Event payloads are matched "
            + "by event name and optionally filtered by expression. For real-time updates, "
            + "use the streaming API (SSE) at /api/agent/stream/{executionId}. Events "
            + "include: tool_start, tool_end, llm_start, llm_end, agent_start, agent_end, "
            + "and token events for incremental output."),
        new Doc("guardrails",
            "Guardrails. Guardrails validate LLM outputs before they reach the user. "
            + "RegexGuardrail matches patterns in block mode (reject if matched) or allow "
            + "mode (reject if not matched). LLMGuardrail uses a secondary LLM to evaluate "
            + "outputs against a policy. Custom @guardrail functions can implement arbitrary "
            + "validation logic. Guardrails support on_fail actions: raise (stop execution), "
            + "retry (ask the LLM to try again, up to max_retries), or fix (replace output "
            + "with a corrected version). Guardrails can be applied at input or output position.")
    );

    // ── RAG tool stubs (static — FunctionTool.create requires static methods) ──

    // In-memory index that simulates Conductor's LLM_INDEX_TEXT / LLM_SEARCH_INDEX.
    private static final Map<String, String> STORE = new LinkedHashMap<>();

    @Schema(description = "Search the product documentation knowledge base. "
                       + "Use this to find relevant documentation before answering questions.")
    public static Map<String, Object> searchKnowledgeBase(
            @Schema(name = "query", description = "Search query") String query) {
        String q = query.toLowerCase();
        List<Map<String, Object>> hits = new ArrayList<>();
        for (Map.Entry<String, String> e : STORE.entrySet()) {
            if (e.getValue().toLowerCase().contains(q)) {
                hits.add(Map.of("docId", e.getKey(), "text", e.getValue()));
            }
        }
        return Map.of(
            "vector_db", "pgvectordb",
            "index", "product_docs",
            "query", query,
            "max_results", 5,
            "results", hits.subList(0, Math.min(5, hits.size()))
        );
    }

    @Schema(description = "Add a new document to the product documentation knowledge base. "
                       + "Use this when the user provides new information that should be stored.")
    public static Map<String, Object> indexDocument(
            @Schema(name = "docId", description = "Document ID") String docId,
            @Schema(name = "text", description = "Document text") String text) {
        STORE.put(docId, text);
        return Map.of(
            "vector_db", "pgvectordb",
            "index", "product_docs",
            "embedding_model_provider", "openai",
            "embedding_model", "text-embedding-3-small",
            "docId", docId,
            "status", "indexed"
        );
    }

    public static void main(String[] args) {
        LlmAgent ragAgent = LlmAgent.builder()
            .name("rag_assistant")
            .description("RAG product-support assistant that indexes and searches a documentation knowledge base.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a product support assistant with access to the documentation
                knowledge base.

                When the user asks you to index or store documents:
                1. Use index_document for EACH document provided
                2. Use the docId and text exactly as given
                3. Confirm each document was indexed

                When the user asks a question:
                1. ALWAYS search the knowledge base first using search_knowledge_base
                2. If relevant documents are found, use them to provide an accurate answer
                3. If no relevant documents are found, say so honestly

                Always cite which documents (by docId) you used in your answer.
                """)
            .tools(
                FunctionTool.create(Example35RagAgent.class, "searchKnowledgeBase"),
                FunctionTool.create(Example35RagAgent.class, "indexDocument"))
            .build();

        // ── Phase 1: Index all documents ─────────────────────────────────
        System.out.println("============================================================");
        System.out.println("PHASE 1: Indexing documents into vector database");
        System.out.println("============================================================");

        StringBuilder indexPrompt = new StringBuilder(
            "Please index the following documents into the knowledge base:\n\n");
        for (Doc doc : DOCUMENTS) {
            indexPrompt.append("DocID: ").append(doc.docId).append('\n');
            indexPrompt.append("Text: ").append(doc.text).append("\n\n");
        }

        AgentResult result = Agentspan.run(ragAgent, indexPrompt.toString());
        result.printResult();

        // ── Phase 2: Search the indexed documents ────────────────────────
        System.out.println("\n============================================================");
        System.out.println("PHASE 2: Searching the knowledge base");
        System.out.println("============================================================");

        List<String> queries = List.of(
            "How do I authenticate my API requests? What are the rate limits?",
            "What retry policies are available for failed tasks?",
            "How do I set up vector search with PostgreSQL?",
            "What multi-agent patterns does the framework support?",
            "How do guardrails work and what happens when validation fails?"
        );

        for (int i = 0; i < queries.size(); i++) {
            String query = queries.get(i);
            System.out.println("\n--- Query " + (i + 1) + ": " + query);
            result = Agentspan.run(ragAgent, query);
            result.printResult();
        }

        Agentspan.shutdown();
    }
}
