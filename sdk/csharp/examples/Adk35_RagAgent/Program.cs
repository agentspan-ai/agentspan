// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk35 — RAG Agent.
//
// A RAG agent flow with index + search tools. The Python source uses
// Agentspan's search_tool / index_tool factories (mapped to Conductor's
// LLM_INDEX_TEXT / LLM_SEARCH_INDEX system tasks).
//
// Note: simplified from Java original — no equivalent search_tool /
// index_tool factory helpers; the C# port stubs the same tool names +
// signatures as in-process functions that record the request and return
// canned shapes — preserving the example flow.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

// ── Knowledge base content to index (mirrors Python DOCUMENTS) ──
var documents = new List<(string DocId, string Text)>
{
    ("auth-guide",
        "API Authentication Guide. To authenticate API requests, include an " +
        "Authorization header with a Bearer token. Tokens can be generated from " +
        "the Settings > API Keys page in the dashboard. Tokens expire after 30 " +
        "days and must be rotated. Service accounts can use long-lived tokens " +
        "by enabling the 'non-expiring' option. Rate limits are applied per-token: " +
        "1000 requests/minute for standard tokens, 5000 for enterprise tokens."),
    ("workflow-tasks",
        "Workflow Task Types. Conductor supports several task types: SIMPLE tasks " +
        "are executed by workers polling for work. HTTP tasks make REST API calls " +
        "directly from the server. INLINE tasks run JavaScript expressions for " +
        "lightweight data transformations. SUB_WORKFLOW tasks invoke another workflow " +
        "as a child. FORK_JOIN_DYNAMIC tasks execute multiple tasks in parallel. " +
        "SWITCH tasks provide conditional branching based on expressions. WAIT tasks " +
        "pause execution until an external signal is received."),
    ("error-handling",
        "Error Handling and Retries. Tasks support configurable retry policies. " +
        "Set retryCount to the number of retry attempts (default 3). retryLogic can " +
        "be FIXED, EXPONENTIAL_BACKOFF, or LINEAR_BACKOFF. retryDelaySeconds sets " +
        "the base delay between retries. Tasks can be marked as optional: true so " +
        "workflow execution continues even if they fail. Use timeoutSeconds to set " +
        "a maximum execution time. The timeoutPolicy can be RETRY, TIME_OUT_WF, or " +
        "ALERT_ONLY. Failed tasks populate reasonForIncompletion with error details."),
    ("agent-configuration",
        "Agent Configuration. Agents are defined with a name, model, instructions, " +
        "and tools. The model field uses the format 'provider/model_name', e.g. " +
        "'openai/gpt-4o' or 'anthropic/claude-sonnet-4-20250514'. Instructions can be " +
        "a string or a PromptTemplate referencing a stored prompt. Tools can be " +
        "@tool-decorated Python functions, http_tool for REST APIs, mcp_tool for " +
        "MCP servers, or agent_tool to wrap another agent as a callable tool. " +
        "Set max_turns to limit the agent's reasoning loop (default 25)."),
    ("vector-search-setup",
        "Vector Search Setup. To enable RAG capabilities, configure a vector database " +
        "in application-rag.properties. Supported backends: pgvectordb (PostgreSQL with " +
        "pgvector extension), pineconedb (Pinecone cloud), and mongodb_atlas (MongoDB " +
        "Atlas Vector Search). For pgvector, install the extension with " +
        "'CREATE EXTENSION vector' and set the JDBC connection string. Embedding " +
        "dimensions default to 1536 (matching text-embedding-3-small). Supported " +
        "distance metrics: cosine (default), euclidean, and inner_product. HNSW " +
        "indexing is recommended for production workloads."),
    ("multi-agent-patterns",
        "Multi-Agent Patterns. SequentialAgent runs sub-agents in order, passing " +
        "state via output_key. ParallelAgent runs sub-agents concurrently and " +
        "aggregates results. LoopAgent repeats a sub-agent up to max_iterations " +
        "times, useful for iterative refinement. For dynamic routing, use a router " +
        "agent or handoff conditions (OnTextMention, OnToolResult, OnCondition). " +
        "The swarm strategy enables peer-to-peer agent delegation. Use " +
        "allowed_transitions to constrain which agents can hand off to which."),
    ("webhook-events",
        "Webhook and Event Configuration. Conductor supports webhook-based task " +
        "completion via WAIT tasks. Configure event handlers with action types: " +
        "complete_task, fail_task, or update_variables. Event payloads are matched " +
        "by event name and optionally filtered by expression. For real-time updates, " +
        "use the streaming API (SSE) at /api/agent/stream/{executionId}. Events " +
        "include: tool_start, tool_end, llm_start, llm_end, agent_start, agent_end, " +
        "and token events for incremental output."),
    ("guardrails",
        "Guardrails. Guardrails validate LLM outputs before they reach the user. " +
        "RegexGuardrail matches patterns in block mode (reject if matched) or allow " +
        "mode (reject if not matched). LLMGuardrail uses a secondary LLM to evaluate " +
        "outputs against a policy. Custom @guardrail functions can implement arbitrary " +
        "validation logic. Guardrails support on_fail actions: raise (stop execution), " +
        "retry (ask the LLM to try again, up to max_retries), or fix (replace output " +
        "with a corrected version). Guardrails can be applied at input or output position."),
};

var ragAgent = GoogleADKAgent.Builder()
    .Name("rag_assistant")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a product support assistant with access to the documentation " +
        "knowledge base.\n\n" +
        "When the user asks you to index or store documents:\n" +
        "1. Use index_document for EACH document provided\n" +
        "2. Use the docId and text exactly as given\n" +
        "3. Confirm each document was indexed\n\n" +
        "When the user asks a question:\n" +
        "1. ALWAYS search the knowledge base first using search_knowledge_base\n" +
        "2. If relevant documents are found, use them to provide an accurate answer\n" +
        "3. If no relevant documents are found, say so honestly\n\n" +
        "Always cite which documents (by docId) you used in your answer.")
    .Tools(new RagTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });

// ── Phase 1: Index all documents ─────────────────────────────────
Console.WriteLine(new string('=', 60));
Console.WriteLine("PHASE 1: Indexing documents into vector database");
Console.WriteLine(new string('=', 60));

var indexPrompt = new System.Text.StringBuilder(
    "Please index the following documents into the knowledge base:\n\n");
foreach (var doc in documents)
{
    indexPrompt.AppendLine($"DocID: {doc.DocId}");
    indexPrompt.AppendLine($"Text: {doc.Text}");
    indexPrompt.AppendLine();
}

var result = await runtime.RunAsync(ragAgent, indexPrompt.ToString());
result.PrintResult();

// ── Phase 2: Search the indexed documents ────────────────────────
Console.WriteLine();
Console.WriteLine(new string('=', 60));
Console.WriteLine("PHASE 2: Searching the knowledge base");
Console.WriteLine(new string('=', 60));

var queries = new[]
{
    "How do I authenticate my API requests? What are the rate limits?",
    "What retry policies are available for failed tasks?",
    "How do I set up vector search with PostgreSQL?",
    "What multi-agent patterns does the framework support?",
    "How do guardrails work and what happens when validation fails?",
};

for (int i = 0; i < queries.Length; i++)
{
    Console.WriteLine($"\n--- Query {i + 1}: {queries[i]}");
    result = await runtime.RunAsync(ragAgent, queries[i]);
    result.PrintResult();
}

internal sealed class RagTools
{
    private readonly Dictionary<string, string> _store = new();

    [Tool(Name = "search_knowledge_base",
        Description = "Search the product documentation knowledge base. " +
                      "Use this to find relevant documentation before answering questions.")]
    public Dictionary<string, object> SearchKnowledgeBase(string query)
    {
        var q = query.ToLowerInvariant();
        var hits = new List<Dictionary<string, object>>();
        foreach (var (k, v) in _store)
        {
            if (v.ToLowerInvariant().Contains(q))
                hits.Add(new Dictionary<string, object> { ["docId"] = k, ["text"] = v });
        }
        return new Dictionary<string, object>
        {
            ["vector_db"]    = "pgvectordb",
            ["index"]        = "product_docs",
            ["query"]        = query,
            ["max_results"]  = 5,
            ["results"]      = hits.Take(5).ToList(),
        };
    }

    [Tool(Name = "index_document",
        Description = "Add a new document to the product documentation knowledge base. " +
                      "Use this when the user provides new information that should be stored.")]
    public Dictionary<string, object> IndexDocument(string docId, string text)
    {
        _store[docId] = text;
        return new Dictionary<string, object>
        {
            ["vector_db"]               = "pgvectordb",
            ["index"]                   = "product_docs",
            ["embedding_model_provider"] = "openai",
            ["embedding_model"]          = "text-embedding-3-small",
            ["docId"]                    = docId,
            ["status"]                   = "indexed",
        };
    }
}
