// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Semantic Memory — long-term memory with similarity-based retrieval.
//
// SemanticMemory stores facts and retrieves the most relevant ones
// for a given query using Jaccard keyword overlap (InMemoryStore).
// The agent calls get_customer_context to inject relevant facts into
// its reasoning before responding.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Build up a knowledge base ────────────────────────────────────────

var memory = new SemanticMemory(maxResults: 3);

memory.Add("The customer's name is Alice and she prefers email communication.");
memory.Add("Alice's account is on the Enterprise plan since March 2021.");
memory.Add("Last interaction: Alice reported a billing discrepancy on invoice #1042.");
memory.Add("Alice's preferred language is English.");
memory.Add("Company policy: Enterprise customers get priority support with 1-hour SLA.");
memory.Add("Alice's timezone is US/Pacific.");

// ── Tool that uses memory for context ────────────────────────────────

var agent = new Agent("memory_agent")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new CustomerContextTool(memory)),
    Instructions =
        "You are a customer support agent with access to a memory system. " +
        "Use the get_customer_context tool to recall relevant information " +
        "about the customer before responding. Always personalize your response.",
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("--- Query 1: Billing question ---");
var result1 = await runtime.RunAsync(
    agent,
    "I have a question about my billing — is there an issue with my account?");
result1.PrintResult();

Console.WriteLine("\n--- Query 2: Plan question ---");
var result2 = await runtime.RunAsync(
    agent,
    "What plan am I on and when did I sign up?");
result2.PrintResult();

Console.WriteLine("\n--- Memory contents ---");
foreach (var entry in memory.ListAll())
    Console.WriteLine($"  [{entry.Id[..8]}] {entry.Content}");

Console.WriteLine("\n--- Search for 'billing invoice' ---");
foreach (var text in memory.Search("billing invoice"))
    Console.WriteLine($"  → {text}");

// ── Tool implementation ───────────────────────────────────────────────

internal sealed class CustomerContextTool(SemanticMemory memory)
{
    [Tool("Retrieve relevant customer context from memory based on the query.")]
    public string GetCustomerContext(string query) => memory.GetContext(query);
}
