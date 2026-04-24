// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Scatter-Gather — massive parallel multi-agent orchestration.
//
// Demonstrates:
//   - Agent.ScatterGather() helper: decompose → fan-out → synthesize
//   - 100 sub-agents running in parallel via FORK_JOIN_DYNAMIC
//   - Coordinator dispatching worker agents in parallel
//   - Durable execution with automatic retries on transient failures
//
// The coordinator analyzes the input, splits it into 100 independent sub-tasks,
// dispatches 100 worker agents in parallel, and synthesizes the results.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Worker tool: simulates a knowledge base lookup ─────────────

var knowledgeBaseTools = ToolRegistry.FromInstance(new KnowledgeBase());

// ── Worker agent: researches a single country ─────────────────

var researcher = new Agent("researcher_58")
{
    Model    = Settings.LlmModel,
    Tools    = knowledgeBaseTools,
    MaxTurns = 5,
    Instructions =
        "You are a country analyst. You will be given the name of a country. " +
        "Use the search_knowledge_base tool ONCE to research that country, then " +
        "immediately write a brief 2-3 sentence profile covering: GDP ranking, " +
        "population, primary industries, and one unique fact. " +
        "Do NOT call the tool more than once — synthesize from the first result.",
};

// ── Coordinator: dispatches 100 parallel researchers ──────────

var countries = new[]
{
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola",
    "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan",
    "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus",
    "Belgium", "Belize", "Benin", "Bhutan", "Bolivia",
    "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria",
    "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada",
    "Chad", "Chile", "China", "Colombia", "Congo",
    "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czech Republic",
    "Denmark", "Djibouti", "Dominican Republic", "Ecuador", "Egypt",
    "El Salvador", "Estonia", "Ethiopia", "Fiji", "Finland",
    "France", "Gabon", "Georgia", "Germany", "Ghana",
    "Greece", "Guatemala", "Guinea", "Haiti", "Honduras",
    "Hungary", "Iceland", "India", "Indonesia", "Iran",
    "Iraq", "Ireland", "Israel", "Italy", "Jamaica",
    "Japan", "Jordan", "Kazakhstan", "Kenya", "Kuwait",
    "Laos", "Latvia", "Lebanon", "Libya", "Lithuania",
    "Luxembourg", "Madagascar", "Malaysia", "Mali", "Malta",
    "Mexico", "Mongolia", "Morocco", "Mozambique", "Myanmar",
    "Nepal", "Netherlands", "New Zealand", "Nigeria", "North Korea",
    "Norway", "Oman", "Pakistan", "Panama", "Paraguay",
};

var countryList = string.Join("\n", countries.Select((c, i) => $"{i + 1}. {c}"));

var coordinator = Agent.ScatterGather(
    name:             "coordinator_58",
    worker:           researcher,
    model:            Settings.LlmModel,
    instructions:
        $"You MUST create EXACTLY {countries.Length} researcher calls — one per " +
        $"country below. Each call should pass just the country name as the " +
        $"request. Issue ALL calls in a SINGLE response.\n\n" +
        $"Countries:\n{countryList}\n\n" +
        $"After all {countries.Length} results return, compile a 'Global Country " +
        $"Profiles' report organized by continent, with a brief summary table " +
        $"at the top showing the top 10 countries by GDP.",
    retryCount:        3,
    retryDelaySeconds: 5,
    timeoutSeconds:    600);

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

var prompt = $"Create a comprehensive profile for each of the {countries.Length} countries listed.";

Console.WriteLine(new string('=', 70));
Console.WriteLine($"  Scatter-Gather: {countries.Length} Parallel Sub-Agents");
Console.WriteLine($"  Coordinator and Workers: {Settings.LlmModel}");
Console.WriteLine(new string('=', 70));
Console.WriteLine($"\nPrompt: {prompt}");
Console.WriteLine($"Countries: {countries.Length}");
Console.WriteLine($"Dispatching {countries.Length} parallel researcher agents...\n");

var result = await runtime.RunAsync(coordinator, prompt);
Console.WriteLine("--- Coordinator Result ---");
result.PrintResult();

// ── Tool class ─────────────────────────────────────────────────

internal sealed class KnowledgeBase
{
    [Tool("Search the knowledge base for information on a topic. Returns relevant facts.")]
    public Dictionary<string, object> SearchKnowledgeBase(string query)
    {
        return new()
        {
            ["query"]   = query,
            ["results"] = new[]
            {
                $"Key finding about {query}: widely used in production systems",
                $"Community perspective on {query}: growing ecosystem",
                $"Performance benchmark for {query}: competitive in its niche",
            },
        };
    }
}
