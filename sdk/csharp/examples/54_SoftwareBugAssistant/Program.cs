// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Software Bug Assistant — AgentTool + MCP for bug triage.
//
// Demonstrates:
//   - AgentTool wrapping a search sub-agent
//   - McpTools.Create() for live GitHub issue/PR lookup
//   - Local @tool for in-memory ticket CRUD
//
// Requirements:
//   - Agentspan server with MCP support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment
//   - GH_TOKEN in environment (for GitHub MCP server)

using Agentspan;
using Agentspan.Examples;

// ── In-memory ticket store ────────────────────────────────────

// ── GitHub MCP tool (server-side, no worker needed) ───────────

var ghMcpTool = McpTools.Create(
    serverUrl:   "https://api.githubcopilot.com/mcp",
    name:        "github_issues",
    description: "Search GitHub issues and PRs on the conductor-oss/conductor repository.",
    headers:     new() { ["Authorization"] = "${GH_TOKEN}" },
    credentials: ["GH_TOKEN"]);

// ── Search sub-agent (wrapped as an AgentTool) ─────────────────

var searchAgent = new Agent("ticket_searcher_54")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a ticket search agent. Search the in-memory ticket database " +
        "using search_tickets and look up GitHub issues with github_issues. " +
        "Return a concise summary of relevant tickets.",
    Tools = [.. ToolRegistry.FromInstance(new TicketTools()), ghMcpTool],
};

var searchTool = AgentTool.Create(
    searchAgent,
    name:        "search_bugs",
    description: "Search internal tickets and GitHub issues for a given bug or topic.");

// ── Bug assistant ─────────────────────────────────────────────

var bugAssistant = new Agent("bug_assistant_54")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a software bug assistant. Help users understand, prioritize, " +
        "and manage bug reports. Use search_bugs to find related issues. " +
        "Use the ticket tools to create and update tickets.",
    Tools = [searchTool, .. ToolRegistry.FromInstance(new TicketTools())],
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    bugAssistant,
    "What open high-priority bugs do we have? List the top issues.");

result.PrintResult();

// ── Tool class ────────────────────────────────────────────────

internal sealed class TicketTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> Tickets = new()
    {
        ["COND-001"] = new()
        {
            ["id"] = "COND-001", ["title"] = "TaskStatusListener not invoked for system task lifecycle transitions",
            ["status"] = "open", ["priority"] = "high", ["github_issue"] = 847,
        },
        ["COND-002"] = new()
        {
            ["id"] = "COND-002", ["title"] = "Support reasonForIncompletion in fail_task event handlers",
            ["status"] = "open", ["priority"] = "medium", ["github_issue"] = 858,
        },
        ["COND-003"] = new()
        {
            ["id"] = "COND-003", ["title"] = "Optimize /workflowDefs page: paginate latest-versions API",
            ["status"] = "open", ["priority"] = "medium", ["github_issue"] = 781,
        },
    };

    [Tool("Search the internal bug ticket database for Conductor issues.")]
    public Dictionary<string, object> SearchTickets(string query, string status = "open")
    {
        var lower = query.ToLower();
        var matches = Tickets.Values
            .Where(t => t["status"].ToString() == status &&
                        (t["title"].ToString()!.ToLower().Contains(lower) ||
                         t["id"].ToString()!.ToLower().Contains(lower)))
            .ToList();
        return new() { ["matches"] = matches, ["count"] = matches.Count };
    }

    [Tool("Get a ticket by ID.")]
    public Dictionary<string, object> GetTicket(string ticketId)
        => Tickets.TryGetValue(ticketId.ToUpper(), out var t) ? t
           : new() { ["error"] = $"Ticket {ticketId} not found" };

    [Tool("Get today's date.")]
    public Dictionary<string, object> GetCurrentDate()
        => new() { ["date"] = DateTime.UtcNow.ToString("yyyy-MM-dd") };
}
