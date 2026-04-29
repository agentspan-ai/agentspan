// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.RagTools;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.util.List;

/**
 * Example 56 — RAG Agent (Retrieval-Augmented Generation)
 *
 * <p>Demonstrates an agent that indexes documents into a vector database and
 * then answers questions by searching the indexed content.
 *
 * <pre>
 * indexer_agent
 *   └── index_doc (RagTools.indexTool)
 *
 * qa_agent
 *   └── search_docs (RagTools.searchTool)
 * </pre>
 *
 * <p>Requires a pgvectordb integration configured in the Conductor server.
 */
public class Example56RagAgent {

    private static final String VECTOR_DB      = "pgvectordb";
    private static final String INDEX          = "agentspan_docs_56";
    private static final String EMBED_PROVIDER = "openai";
    private static final String EMBED_MODEL    = "text-embedding-3-small";

    public static void main(String[] args) {
        // ── Tools ────────────────────────────────────────────────────────────

        ToolDef indexTool = RagTools.indexTool(
            "index_doc",
            "Index a document into the knowledge base",
            VECTOR_DB, INDEX, EMBED_PROVIDER, EMBED_MODEL);

        ToolDef searchTool = RagTools.searchTool(
            "search_docs",
            "Search the knowledge base for relevant information",
            VECTOR_DB, INDEX, EMBED_PROVIDER, EMBED_MODEL, 3);

        // ── Indexer agent: loads documents ───────────────────────────────────

        Agent indexerAgent = Agent.builder()
            .name("indexer_agent_56")
            .model(Settings.LLM_MODEL)
            .tools(List.of(indexTool))
            .instructions(
                "You are a document indexer. When given documents to index, call index_doc " +
                "once per document with the full text and a short docId derived from the title. " +
                "After all documents are indexed, confirm how many were indexed.")
            .build();

        System.out.println("=== Phase 1: Indexing documents ===");
        AgentResult indexResult = Agentspan.run(indexerAgent,
            "Index the following documents:\n\n" +
            "Title: Agentspan Overview\n" +
            "Content: Agentspan is a multi-agent orchestration platform built on Conductor. " +
            "It enables developers to build, deploy, and manage AI agent workflows at scale. " +
            "Agents can use tools, call sub-agents, and maintain shared state.\n\n" +
            "Title: Agent Strategies\n" +
            "Content: Agentspan supports multiple agent strategies: ROUTER (LLM picks the next agent), " +
            "HANDOFF (transfer control to another agent), SWARM (agents collaborate simultaneously), " +
            "and LOOP (repeat until a condition is met). Each strategy suits different workflow patterns.\n\n" +
            "Title: Tool Types\n" +
            "Content: Agentspan tools include local Python/Java workers, RAG search/index tools, " +
            "HTTP tools for calling REST APIs, and AgentTool for calling sub-agents. " +
            "Tools are registered with name, description, and JSON schema for the LLM.\n\n" +
            "Title: Guardrails\n" +
            "Content: Guardrails validate agent actions before or after execution. " +
            "INPUT guardrails check tool inputs, OUTPUT guardrails validate results. " +
            "On failure, guardrails can FAIL the workflow, ask the LLM to REPLAN, or pause for HUMAN review.");
        indexResult.printResult();

        // ── QA agent: answers questions ──────────────────────────────────────

        Agent qaAgent = Agent.builder()
            .name("qa_agent_56")
            .model(Settings.LLM_MODEL)
            .tools(List.of(searchTool))
            .instructions(
                "You are a knowledgeable assistant with access to a document knowledge base. " +
                "For each question, search the knowledge base with relevant queries and " +
                "provide a concise, accurate answer based on the retrieved content.")
            .build();

        System.out.println("\n=== Phase 2: Answering questions from indexed docs ===");
        AgentResult qaResult = Agentspan.run(qaAgent,
            "Answer these questions using the knowledge base:\n" +
            "1. What is Agentspan and what platform is it built on?\n" +
            "2. What agent strategies are available and when would you use HANDOFF?\n" +
            "3. What happens when a guardrail fails?");
        qaResult.printResult();

        Agentspan.shutdown();
    }
}
