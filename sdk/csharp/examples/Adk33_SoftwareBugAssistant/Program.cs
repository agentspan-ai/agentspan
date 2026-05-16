// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk33 — Software Bug Assistant.
//
// agent_tool + local CRUD tools for bug triage. The Python source also
// uses an MCP tool for live GitHub access; the C# port omits the MCP
// wiring and keeps a search_web sub-agent + local ticket store.
//
// Note: simplified from Java original — no MCP factory wiring; GitHub
// lookup is documented in instructions but not wired.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var searchAgent = GoogleADKAgent.Builder()
    .Name("search_agent")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a technical search assistant specializing in Conductor " +
        "(conductor-oss/conductor) workflow orchestration. Use the search_web " +
        "tool to find relevant information about bugs, errors, and Conductor " +
        "configuration issues. Provide concise, actionable answers.")
    .Tools(new SearchAgentTools())
    .Build();

var ticketTools = new TicketTools();
var searchAgentTool = AgentTool.Create(searchAgent);

var softwareAssistant = GoogleADKAgent.Builder()
    .Name("software_assistant")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a software bug triage assistant for the Conductor workflow " +
        "orchestration engine (https://github.com/conductor-oss/conductor).\n\n" +
        "Your capabilities:\n" +
        "1. Search and manage internal bug tickets (search_tickets, create_ticket, update_ticket)\n" +
        "2. Research Conductor issues using the search_agent tool\n" +
        "3. Cross-reference internal tickets against known issues\n\n" +
        "When triaging:\n" +
        "- Cross-reference with internal tickets (search_tickets)\n" +
        "- Research any unfamiliar issues with the search_agent\n" +
        "- Create internal tickets for new issues not yet tracked\n" +
        "- Suggest next steps, referencing GitHub issue/PR numbers")
    .Tools(ticketTools)
    .ToolDefs(new[] { searchAgentTool })
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(softwareAssistant,
    "Review the latest open issues and PRs on conductor-oss/conductor. " +
    "Check if any of them relate to our internal tickets. " +
    "Pay attention to the DO_WHILE fix (PR #820) and the scheduler " +
    "persistence PRs. Give me a triage summary.");
result.PrintResult();

internal sealed class TicketTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _tickets = new()
    {
        ["COND-001"] = new()
        {
            ["id"]           = "COND-001",
            ["title"]        = "TaskStatusListener not invoked for system task lifecycle transitions",
            ["status"]       = "open",
            ["priority"]     = "high",
            ["github_issue"] = 847,
            ["description"]  = "TaskStatusListener notifications are only fully wired for " +
                               "worker tasks (SIMPLE/custom). Both synchronous and asynchronous " +
                               "system tasks miss lifecycle transition callbacks.",
            ["created"]      = "2026-03-10",
        },
        ["COND-002"] = new()
        {
            ["id"]           = "COND-002",
            ["title"]        = "Support reasonForIncompletion in fail_task event handlers",
            ["status"]       = "open",
            ["priority"]     = "medium",
            ["github_issue"] = 858,
            ["description"]  = "When an event handler uses action: fail_task, there is no way " +
                               "to set reasonForIncompletion. Need to support this field so " +
                               "failed tasks have meaningful error messages.",
            ["created"]      = "2026-03-13",
        },
        ["COND-003"] = new()
        {
            ["id"]           = "COND-003",
            ["title"]        = "Optimize /workflowDefs page: paginate latest-versions API",
            ["status"]       = "open",
            ["priority"]     = "medium",
            ["github_issue"] = 781,
            ["description"]  = "The UI /workflowDefs page calls GET /metadata/workflow which " +
                               "returns all versions of all workflows. This causes slow page " +
                               "loads. Need pagination for the latest-versions endpoint.",
            ["created"]      = "2026-02-18",
        },
    };
    private static int _nextId = 4;

    [Tool(Name = "get_current_date", Description = "Get today's date.")]
    public Dictionary<string, object> GetCurrentDate()
        => new() { ["date"] = DateTime.UtcNow.ToString("yyyy-MM-dd") };

    [Tool(Name = "search_tickets", Description = "Search the internal bug ticket database for Conductor issues.")]
    public Dictionary<string, object> SearchTickets(string query)
    {
        var q = query.ToLowerInvariant();
        var matches = new List<Dictionary<string, object>>();
        foreach (var t in _tickets.Values)
        {
            var title = ((string)t["title"]).ToLowerInvariant();
            var desc = ((string)t["description"]).ToLowerInvariant();
            if (title.Contains(q) || desc.Contains(q)) matches.Add(t);
        }
        return new Dictionary<string, object>
        {
            ["query"]   = query,
            ["count"]   = matches.Count,
            ["tickets"] = matches,
        };
    }

    [Tool(Name = "create_ticket", Description = "Create a new bug ticket in the internal tracker.")]
    public Dictionary<string, object> CreateTicket(string title, string description, string priority)
    {
        var ticketId = $"COND-{_nextId++:000}";
        var p = string.IsNullOrEmpty(priority) ? "medium" : priority;
        var ticket = new Dictionary<string, object>
        {
            ["id"]          = ticketId,
            ["title"]       = title,
            ["status"]      = "open",
            ["priority"]    = p,
            ["description"] = description,
            ["created"]     = DateTime.UtcNow.ToString("yyyy-MM-dd"),
        };
        _tickets[ticketId] = ticket;
        return new Dictionary<string, object> { ["created"] = true, ["ticket"] = ticket };
    }

    [Tool(Name = "update_ticket", Description = "Update an existing bug ticket's status or priority.")]
    public Dictionary<string, object> UpdateTicket(string ticket_id, string status, string priority)
    {
        if (!_tickets.TryGetValue(ticket_id.ToUpperInvariant(), out var ticket))
            return new Dictionary<string, object> { ["error"] = $"Ticket {ticket_id} not found" };
        if (!string.IsNullOrEmpty(status))   ticket["status"]   = status;
        if (!string.IsNullOrEmpty(priority)) ticket["priority"] = priority;
        return new Dictionary<string, object> { ["updated"] = true, ["ticket"] = ticket };
    }
}

internal sealed class SearchAgentTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _results = new()
    {
        ["task status listener"] = new()
        {
            ["source"] = "Conductor Docs",
            ["answer"] = "TaskStatusListener is only wired for SIMPLE tasks. System " +
                         "tasks like HTTP, INLINE, SUB_WORKFLOW bypass the listener " +
                         "because they complete synchronously within the decider loop.",
        },
        ["do_while loop"] = new()
        {
            ["source"] = "GitHub PR #820",
            ["answer"] = "DO_WHILE tasks with 'items' now pass validation without " +
                         "loopCondition. Fixed in PR #820 — the validator was " +
                         "unconditionally requiring loopCondition for all DO_WHILE tasks.",
        },
        ["event handler fail"] = new()
        {
            ["source"] = "GitHub Issue #858",
            ["answer"] = "Event handlers with action: fail_task cannot set " +
                         "reasonForIncompletion. A proposed fix adds an optional " +
                         "'reason' field to the fail_task action configuration.",
        },
        ["workflow def pagination"] = new()
        {
            ["source"] = "GitHub Issue #781",
            ["answer"] = "The /metadata/workflow endpoint returns all versions of all " +
                         "workflows causing slow UI loads. A pagination API for " +
                         "latest-versions is proposed to fix this.",
        },
    };

    [Tool(Name = "search_web",
        Description = "Search the web for information about a Conductor bug or workflow issue.")]
    public Dictionary<string, object> SearchWeb(string query)
    {
        var q = query.ToLowerInvariant();
        foreach (var (k, v) in _results)
        {
            if (q.Contains(k))
            {
                var r = new Dictionary<string, object>
                {
                    ["query"] = query, ["found"] = true,
                };
                foreach (var (kk, vv) in v) r[kk] = vv;
                return r;
            }
        }
        return new Dictionary<string, object>
        {
            ["query"] = query, ["found"] = false, ["summary"] = "No specific results found.",
        };
    }
}
