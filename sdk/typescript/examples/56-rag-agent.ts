/**
 * 56 - RAG Agent — vector search + document indexing.
 *
 * Demonstrates:
 *   - indexTool to populate a vector database with documents
 *   - searchTool to query the indexed documents
 *
 * Requirements:
 *   - Conductor server with RAG system tasks enabled
 *   - A configured vector database (e.g., pgvector)
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, searchTool, indexTool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Knowledge base content to index -----------------------------------------

const DOCUMENTS = [
  {
    docId: 'auth-guide',
    text:
      'API Authentication Guide. To authenticate API requests, include an ' +
      'Authorization header with a Bearer token. Tokens can be generated from ' +
      'the Settings > API Keys page in the dashboard. Tokens expire after 30 ' +
      'days and must be rotated. Service accounts can use long-lived tokens ' +
      "by enabling the 'non-expiring' option. Rate limits are applied per-token: " +
      '1000 requests/minute for standard tokens, 5000 for enterprise tokens.',
  },
  {
    docId: 'workflow-tasks',
    text:
      'Workflow Task Types. Conductor supports several task types: SIMPLE tasks ' +
      'are executed by workers polling for work. HTTP tasks make REST API calls ' +
      'directly from the server. INLINE tasks run JavaScript expressions for ' +
      'lightweight data transformations. SUB_WORKFLOW tasks invoke another workflow ' +
      'as a child. FORK_JOIN_DYNAMIC tasks execute multiple tasks in parallel. ' +
      'SWITCH tasks provide conditional branching based on expressions. WAIT tasks ' +
      'pause execution until an external signal is received.',
  },
  {
    docId: 'error-handling',
    text:
      'Error Handling and Retries. Tasks support configurable retry policies. ' +
      'Set retryCount to the number of retry attempts (default 3). retryLogic can ' +
      'be FIXED, EXPONENTIAL_BACKOFF, or LINEAR_BACKOFF. retryDelaySeconds sets ' +
      'the base delay between retries. Tasks can be marked as optional: true so ' +
      'workflow execution continues even if they fail. Use timeoutSeconds to set ' +
      'a maximum execution time. The timeoutPolicy can be RETRY, TIME_OUT_WF, or ' +
      'ALERT_ONLY. Failed tasks populate reasonForIncompletion with error details.',
  },
  {
    docId: 'agent-configuration',
    text:
      "Agent Configuration. Agents are defined with a name, model, instructions, " +
      "and tools. The model field uses the format 'provider/model_name', e.g. " +
      "'openai/gpt-4o' or 'anthropic/claude-sonnet-4-20250514'. Instructions can be " +
      'a string or a PromptTemplate referencing a stored prompt. Tools can be ' +
      '@tool-decorated Python functions, http_tool for REST APIs, mcp_tool for ' +
      'MCP servers, or agent_tool to wrap another agent as a callable tool. ' +
      'Set max_turns to limit the agent\'s reasoning loop (default 25).',
  },
  {
    docId: 'vector-search-setup',
    text:
      'Vector Search Setup. To enable RAG capabilities, configure a vector database ' +
      'in application-rag.properties. Supported backends: pgvectordb (PostgreSQL with ' +
      'pgvector extension), pineconedb (Pinecone cloud), and mongodb_atlas (MongoDB ' +
      "Atlas Vector Search). For pgvector, install the extension with " +
      "'CREATE EXTENSION vector' and set the JDBC connection string. Embedding " +
      'dimensions default to 1536 (matching text-embedding-3-small). Supported ' +
      'distance metrics: cosine (default), euclidean, and inner_product. HNSW ' +
      'indexing is recommended for production workloads.',
  },
  {
    docId: 'multi-agent-patterns',
    text:
      'Multi-Agent Patterns. SequentialAgent runs sub-agents in order, passing ' +
      'state via output_key. ParallelAgent runs sub-agents concurrently and ' +
      'aggregates results. LoopAgent repeats a sub-agent up to max_iterations ' +
      'times, useful for iterative refinement. For dynamic routing, use a router ' +
      'agent or handoff conditions (OnTextMention, OnToolResult, OnCondition). ' +
      'The swarm strategy enables peer-to-peer agent delegation. Use ' +
      'allowed_transitions to constrain which agents can hand off to which.',
  },
  {
    docId: 'webhook-events',
    text:
      'Webhook and Event Configuration. Conductor supports webhook-based task ' +
      'completion via WAIT tasks. Configure event handlers with action types: ' +
      'complete_task, fail_task, or update_variables. Event payloads are matched ' +
      'by event name and optionally filtered by expression. For real-time updates, ' +
      'use the streaming API (SSE) at /api/agent/stream/{executionId}. Events ' +
      'include: tool_start, tool_end, llm_start, llm_end, agent_start, agent_end, ' +
      'and token events for incremental output.',
  },
  {
    docId: 'guardrails',
    text:
      'Guardrails. Guardrails validate LLM outputs before they reach the user. ' +
      'RegexGuardrail matches patterns in block mode (reject if matched) or allow ' +
      'mode (reject if not matched). LLMGuardrail uses a secondary LLM to evaluate ' +
      'outputs against a policy. Custom @guardrail functions can implement arbitrary ' +
      'validation logic. Guardrails support on_fail actions: raise (stop execution), ' +
      'retry (ask the LLM to try again, up to max_retries), or fix (replace output ' +
      'with a corrected version). Guardrails can be applied at input or output position.',
  },
];

// -- RAG tools ---------------------------------------------------------------

const kbSearch = searchTool({
  name: 'search_knowledge_base',
  description:
    'Search the product documentation knowledge base. ' +
    'Use this to find relevant documentation before answering questions.',
  vectorDb: 'pgvectordb',
  index: 'product_docs',
  embeddingModelProvider: 'openai',
  embeddingModel: 'text-embedding-3-small',
  maxResults: 5,
});

const kbIndex = indexTool({
  name: 'index_document',
  description:
    'Add a new document to the product documentation knowledge base. ' +
    'Use this when the user provides new information that should be stored.',
  vectorDb: 'pgvectordb',
  index: 'product_docs',
  embeddingModelProvider: 'openai',
  embeddingModel: 'text-embedding-3-small',
});

// -- Agent -------------------------------------------------------------------

export const ragAgent = new Agent({
  name: 'rag_assistant',
  model: llmModel,
  instructions:
    'You are a product support assistant with access to the documentation ' +
    'knowledge base.\n\n' +
    'When the user asks you to index or store documents:\n' +
    '1. Use index_document for EACH document provided\n' +
    '2. Use the docId and text exactly as given\n' +
    '3. Confirm each document was indexed\n\n' +
    'When the user asks a question:\n' +
    '1. ALWAYS search the knowledge base first using search_knowledge_base\n' +
    '2. If relevant documents are found, use them to provide an accurate answer\n' +
    '3. If no relevant documents are found, say so honestly\n\n' +
    'Always cite which documents (by docId) you used in your answer.',
  tools: [kbSearch, kbIndex],
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Phase 1: Index all documents into the vector database
    console.log('='.repeat(60));
    console.log('PHASE 1: Indexing documents into vector database');
    console.log('='.repeat(60));

    const indexLines = ['Please index the following documents into the knowledge base:\n'];
    for (const doc of DOCUMENTS) {
      indexLines.push(`DocID: ${doc.docId}`);
      indexLines.push(`Text: ${doc.text}\n`);
    }
    const indexPrompt = indexLines.join('\n');

    const indexResult = await runtime.run(ragAgent, indexPrompt);
    indexResult.printResult();

    // Phase 2: Search the indexed documents
    console.log('\n' + '='.repeat(60));
    console.log('PHASE 2: Searching the knowledge base');
    console.log('='.repeat(60));

    const queries = [
    'How do I authenticate my API requests? What are the rate limits?',
    'What retry policies are available for failed tasks?',
    'How do I set up vector search with PostgreSQL?',
    'What multi-agent patterns does the framework support?',
    'How do guardrails work and what happens when validation fails?',
    ];

    for (let i = 0; i < queries.length; i++) {
      console.log(`\n--- Query ${i + 1}: ${queries[i]}`);
      const result = await runtime.run(ragAgent, queries[i]);
      result.printResult();
    }

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(ragAgent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(ragAgent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('56-rag-agent.ts') || process.argv[1]?.endsWith('56-rag-agent.js')) {
  main().catch(console.error);
}
