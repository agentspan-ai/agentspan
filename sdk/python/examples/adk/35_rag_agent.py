# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK RAG Agent — vector search + document indexing.

Mirrors the pattern from google/adk-samples/RAG but uses Conductor's native
RAG system tasks (LLM_INDEX_TEXT, LLM_SEARCH_INDEX) instead of Vertex AI
RAG Engine.

Demonstrates:
    - index_tool to populate a vector database with documents
    - search_tool to query the indexed documents
    - End-to-end validation: index first, then search

Architecture:
    rag_assistant (root agent)
      tools:
        - search_knowledge_base  # search_tool → LLM_SEARCH_INDEX
        - index_document         # index_tool → LLM_INDEX_TEXT

Supported vector databases:
    - pgvectordb (PostgreSQL + pgvector)
    - pineconedb (Pinecone)
    - mongodb_atlas (MongoDB Atlas Vector Search)

Requirements:
    - pip install google-adk
    - Conductor server with RAG system tasks enabled (--spring.profiles.active=rag)
    - A configured vector database (e.g., pgvector)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, search_tool, index_tool

from settings import settings


# ── Knowledge base content to index ──────────────────────────────────

DOCUMENTS = [
    {
        "docId": "auth-guide",
        "text": (
            "API Authentication Guide. To authenticate API requests, include an "
            "Authorization header with a Bearer token. Tokens can be generated from "
            "the Settings > API Keys page in the dashboard. Tokens expire after 30 "
            "days and must be rotated. Service accounts can use long-lived tokens "
            "by enabling the 'non-expiring' option. Rate limits are applied per-token: "
            "1000 requests/minute for standard tokens, 5000 for enterprise tokens."
        ),
    },
    {
        "docId": "workflow-tasks",
        "text": (
            "Workflow Task Types. Conductor supports several task types: SIMPLE tasks "
            "are executed by workers polling for work. HTTP tasks make REST API calls "
            "directly from the server. INLINE tasks run JavaScript expressions for "
            "lightweight data transformations. SUB_WORKFLOW tasks invoke another workflow "
            "as a child. FORK_JOIN_DYNAMIC tasks execute multiple tasks in parallel. "
            "SWITCH tasks provide conditional branching based on expressions. WAIT tasks "
            "pause execution until an external signal is received."
        ),
    },
    {
        "docId": "error-handling",
        "text": (
            "Error Handling and Retries. Tasks support configurable retry policies. "
            "Set retryCount to the number of retry attempts (default 3). retryLogic can "
            "be FIXED, EXPONENTIAL_BACKOFF, or LINEAR_BACKOFF. retryDelaySeconds sets "
            "the base delay between retries. Tasks can be marked as optional: true so "
            "workflow execution continues even if they fail. Use timeoutSeconds to set "
            "a maximum execution time. The timeoutPolicy can be RETRY, TIME_OUT_WF, or "
            "ALERT_ONLY. Failed tasks populate reasonForIncompletion with error details."
        ),
    },
    {
        "docId": "agent-configuration",
        "text": (
            "Agent Configuration. Agents are defined with a name, model, instructions, "
            "and tools. The model field uses the format 'provider/model_name', e.g. "
            "'openai/gpt-4o' or 'anthropic/claude-sonnet-4-20250514'. Instructions can be "
            "a string or a PromptTemplate referencing a stored prompt. Tools can be "
            "@tool-decorated Python functions, http_tool for REST APIs, mcp_tool for "
            "MCP servers, or agent_tool to wrap another agent as a callable tool. "
            "Set max_turns to limit the agent's reasoning loop (default 25)."
        ),
    },
    {
        "docId": "vector-search-setup",
        "text": (
            "Vector Search Setup. To enable RAG capabilities, configure a vector database "
            "in application-rag.properties. Supported backends: pgvectordb (PostgreSQL with "
            "pgvector extension), pineconedb (Pinecone cloud), and mongodb_atlas (MongoDB "
            "Atlas Vector Search). For pgvector, install the extension with "
            "'CREATE EXTENSION vector' and set the JDBC connection string. Embedding "
            "dimensions default to 1536 (matching text-embedding-3-small). Supported "
            "distance metrics: cosine (default), euclidean, and inner_product. HNSW "
            "indexing is recommended for production workloads."
        ),
    },
    {
        "docId": "multi-agent-patterns",
        "text": (
            "Multi-Agent Patterns. SequentialAgent runs sub-agents in order, passing "
            "state via output_key. ParallelAgent runs sub-agents concurrently and "
            "aggregates results. LoopAgent repeats a sub-agent up to max_iterations "
            "times, useful for iterative refinement. For dynamic routing, use a router "
            "agent or handoff conditions (OnTextMention, OnToolResult, OnCondition). "
            "The swarm strategy enables peer-to-peer agent delegation. Use "
            "allowed_transitions to constrain which agents can hand off to which."
        ),
    },
    {
        "docId": "webhook-events",
        "text": (
            "Webhook and Event Configuration. Conductor supports webhook-based task "
            "completion via WAIT tasks. Configure event handlers with action types: "
            "complete_task, fail_task, or update_variables. Event payloads are matched "
            "by event name and optionally filtered by expression. For real-time updates, "
            "use the streaming API (SSE) at /api/agent/stream/{workflowId}. Events "
            "include: tool_start, tool_end, llm_start, llm_end, agent_start, agent_end, "
            "and token events for incremental output."
        ),
    },
    {
        "docId": "guardrails",
        "text": (
            "Guardrails. Guardrails validate LLM outputs before they reach the user. "
            "RegexGuardrail matches patterns in block mode (reject if matched) or allow "
            "mode (reject if not matched). LLMGuardrail uses a secondary LLM to evaluate "
            "outputs against a policy. Custom @guardrail functions can implement arbitrary "
            "validation logic. Guardrails support on_fail actions: raise (stop execution), "
            "retry (ask the LLM to try again, up to max_retries), or fix (replace output "
            "with a corrected version). Guardrails can be applied at input or output position."
        ),
    },
]


# ── RAG tools ────────────────────────────────────────────────────────

kb_search = search_tool(
    name="search_knowledge_base",
    description="Search the product documentation knowledge base. "
                "Use this to find relevant documentation before answering questions.",
    vector_db="pgvectordb",
    index="product_docs",
    embedding_model_provider="openai",
    embedding_model="text-embedding-3-small",
    max_results=5,
)

kb_index = index_tool(
    name="index_document",
    description="Add a new document to the product documentation knowledge base. "
                "Use this when the user provides new information that should be stored.",
    vector_db="pgvectordb",
    index="product_docs",
    embedding_model_provider="openai",
    embedding_model="text-embedding-3-small",
)


# ── Agent ────────────────────────────────────────────────────────────

rag_agent = Agent(
    name="rag_assistant",
    model=settings.llm_model,
    instructions=(
        "You are a product support assistant with access to the documentation "
        "knowledge base.\n\n"
        "When the user asks you to index or store documents:\n"
        "1. Use index_document for EACH document provided\n"
        "2. Use the docId and text exactly as given\n"
        "3. Confirm each document was indexed\n\n"
        "When the user asks a question:\n"
        "1. ALWAYS search the knowledge base first using search_knowledge_base\n"
        "2. If relevant documents are found, use them to provide an accurate answer\n"
        "3. If no relevant documents are found, say so honestly\n\n"
        "Always cite which documents (by docId) you used in your answer."
    ),
    tools=[kb_search, kb_index],
)


# ── Runner ───────────────────────────────────────────────────────────


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.35_rag_agent
        runtime.deploy(rag_agent)
        runtime.serve(rag_agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # ── Phase 1: Index all documents into the vector database ────────
        # print("=" * 60)
        # print("PHASE 1: Indexing documents into vector database")
        # print("=" * 60)

        # # Build a single prompt that asks the agent to index all documents
        # index_lines = ["Please index the following documents into the knowledge base:\n"]
        # for doc in DOCUMENTS:
        # index_lines.append(f"DocID: {doc['docId']}")
        # index_lines.append(f"Text: {doc['text']}\n")
        # index_prompt = "\n".join(index_lines)

        # result = runtime.run(rag_agent, index_prompt)
        # print(result.output)

        # # ── Phase 2: Search the indexed documents ────────────────────────
        # print("\n" + "=" * 60)
        # print("PHASE 2: Searching the knowledge base")
        # print("=" * 60)

        # queries = [
        # "How do I authenticate my API requests? What are the rate limits?",
        # "What retry policies are available for failed tasks?",
        # "How do I set up vector search with PostgreSQL?",
        # "What multi-agent patterns does the framework support?",
        # "How do guardrails work and what happens when validation fails?",
        # ]

        # for i, query in enumerate(queries, 1):
        # print(f"\n--- Query {i}: {query}")
        # result = runtime.run(rag_agent, query)
        # print(result.output)
