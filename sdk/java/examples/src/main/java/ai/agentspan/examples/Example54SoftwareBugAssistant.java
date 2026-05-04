// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.AgentTool;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;
import ai.agentspan.tools.McpTool;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Example 54 — Software Bug Assistant
 *
 * <p>Demonstrates combining agent-as-a-tool, MCP tools, and regular worker
 * tools in one root agent for bug triage.
 *
 * <pre>
 * software_assistant_54
 *   tools:
 *     - get_current_date         ← worker
 *     - agent_tool(search_agent) ← sub-agent for web research
 *     - github_mcp               ← GitHub MCP tools
 *     - search_tickets           ← ticket database
 *     - create_ticket            ← open new ticket
 *     - update_ticket            ← change status/priority
 * </pre>
 */
public class Example54SoftwareBugAssistant {

    private static final Map<String, Map<String, Object>> TICKETS = new LinkedHashMap<>();
    private static final AtomicInteger NEXT_ID = new AtomicInteger(4);

    static {
        TICKETS.put("COND-001", ticket("COND-001",
            "TaskStatusListener not invoked for system task lifecycle transitions",
            "open", "high", "2026-03-10"));
        TICKETS.put("COND-002", ticket("COND-002",
            "Support reasonForIncompletion in fail_task event handlers",
            "open", "medium", "2026-03-13"));
        TICKETS.put("COND-003", ticket("COND-003",
            "Optimize /workflowDefs page: paginate latest-versions API",
            "open", "medium", "2026-02-18"));
    }

    private static Map<String, Object> ticket(String id, String title, String status,
            String priority, String created) {
        Map<String, Object> t = new LinkedHashMap<>();
        t.put("id", id); t.put("title", title); t.put("status", status);
        t.put("priority", priority); t.put("created", created);
        return t;
    }

    // ── Tools ──────────────────────────────────────────────────────────

    static class UtilTools {
        @Tool(name = "get_current_date", description = "Get today's date in ISO format")
        public Map<String, Object> getCurrentDate() {
            return Map.of("date", LocalDate.now().toString());
        }
    }

    static class SearchTools {
        @Tool(name = "search_web", description = "Search the web for information about a Conductor bug or workflow issue")
        public Map<String, Object> searchWeb(String query) {
            Map<String, Map<String, Object>> results = Map.of(
                "task status listener", Map.of("source", "Conductor Docs",
                    "answer", "TaskStatusListener is only wired for SIMPLE tasks."),
                "do_while", Map.of("source", "GitHub PR #820",
                    "answer", "DO_WHILE tasks with 'items' now pass validation without loopCondition."),
                "event handler fail", Map.of("source", "GitHub Issue #858",
                    "answer", "Event handlers with action: fail_task cannot set reasonForIncompletion."),
                "workflow def", Map.of("source", "GitHub Issue #781",
                    "answer", "The /metadata/workflow endpoint returns all versions causing slow UI.")
            );
            String q = query.toLowerCase();
            for (Map.Entry<String, Map<String, Object>> e : results.entrySet()) {
                if (q.contains(e.getKey())) {
                    Map<String, Object> r = new LinkedHashMap<>(e.getValue());
                    r.put("query", query); r.put("found", true);
                    return r;
                }
            }
            return Map.of("query", query, "found", false, "summary", "No specific results found.");
        }
    }

    static class TicketTools {
        @Tool(name = "search_tickets", description = "Search the internal bug ticket database")
        public Map<String, Object> searchTickets(String query) {
            String q = query.toLowerCase();
            List<Map<String, Object>> matches = new ArrayList<>();
            for (Map<String, Object> t : TICKETS.values()) {
                String title = t.getOrDefault("title", "").toString().toLowerCase();
                if (title.contains(q) || q.contains("all") || q.contains("open")) matches.add(t);
            }
            return Map.of("query", query, "count", matches.size(), "tickets", matches);
        }

        @Tool(name = "create_ticket", description = "Create a new bug ticket")
        public Map<String, Object> createTicket(String title, String description, String priority) {
            String id = "COND-" + String.format("%03d", NEXT_ID.getAndIncrement());
            Map<String, Object> t = ticket(id, title, "open",
                priority != null && !priority.isEmpty() ? priority : "medium",
                LocalDate.now().toString());
            t.put("description", description);
            TICKETS.put(id, t);
            return Map.of("created", true, "ticket", t);
        }

        @Tool(name = "update_ticket", description = "Update an existing bug ticket status or priority")
        public Map<String, Object> updateTicket(String ticketId, String status, String priority) {
            Map<String, Object> t = TICKETS.get(ticketId.toUpperCase());
            if (t == null) return Map.of("error", "Ticket " + ticketId + " not found");
            if (status != null && !status.isEmpty()) t.put("status", status);
            if (priority != null && !priority.isEmpty()) t.put("priority", priority);
            return Map.of("updated", true, "ticket", t);
        }
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) {
        // ── Search sub-agent ────────────────────────────────────────────────
        List<ToolDef> searchTools = ToolRegistry.fromInstance(new SearchTools());
        Agent searchAgent = Agent.builder()
            .name("search_agent_54")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a technical search assistant specializing in Conductor "
                + "workflow orchestration. Use the search_web tool to find relevant "
                + "information about bugs, errors, and Conductor configuration issues. "
                + "Provide concise, actionable answers.")
            .tools(searchTools)
            .build();

        // ── Ticket tools (create_ticket: priority optional; update_ticket: only ticketId required) ──
        List<ToolDef> rawTicketTools = ToolRegistry.fromInstance(new TicketTools());

        ToolDef rawCreate = rawTicketTools.get(1); // create_ticket
        Map<String, Object> createSchema = new LinkedHashMap<>((Map<String, Object>) rawCreate.getInputSchema());
        createSchema.put("required", List.of("title", "description"));
        ToolDef createTool = ToolDef.builder()
            .name(rawCreate.getName()).description(rawCreate.getDescription())
            .inputSchema(createSchema).outputSchema(rawCreate.getOutputSchema())
            .toolType(rawCreate.getToolType()).func(rawCreate.getFunc()).build();

        ToolDef rawUpdate = rawTicketTools.get(2); // update_ticket
        Map<String, Object> updateSchema = new LinkedHashMap<>((Map<String, Object>) rawUpdate.getInputSchema());
        updateSchema.put("required", List.of("ticketId"));
        ToolDef updateTool = ToolDef.builder()
            .name(rawUpdate.getName()).description(rawUpdate.getDescription())
            .inputSchema(updateSchema).outputSchema(rawUpdate.getOutputSchema())
            .toolType(rawUpdate.getToolType()).func(rawUpdate.getFunc()).build();

        // ── GitHub MCP tool ─────────────────────────────────────────────────
        String githubMcpUrl = System.getenv().getOrDefault(
            "GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/");
        String ghToken = System.getenv().getOrDefault("GH_TOKEN", "");
        ToolDef githubMcp = McpTool.builder()
            .name("github_mcp")
            .description("GitHub tools for accessing the conductor-oss/conductor repository — "
                + "search issues, list open pull requests, and get issue details")
            .serverUrl(githubMcpUrl)
            .header("Authorization", "Bearer " + ghToken)
            .build();

        // ── get_current_date tool ───────────────────────────────────────────
        List<ToolDef> utilTools = ToolRegistry.fromInstance(new UtilTools());

        // ── Root agent: tools ordered to match Python ───────────────────────
        // Python order: [get_current_date, agent_tool(search_agent), github_mcp,
        //                search_tickets, create_ticket, update_ticket]
        List<ToolDef> allTools = new ArrayList<>();
        allTools.addAll(utilTools);                        // get_current_date
        allTools.add(AgentTool.from(searchAgent));         // agent_tool
        allTools.add(githubMcp);                           // mcp
        allTools.add(rawTicketTools.get(0));               // search_tickets
        allTools.add(createTool);                          // create_ticket (priority optional)
        allTools.add(updateTool);                          // update_ticket (only ticketId required)

        Agent assistant = Agent.builder()
            .name("software_assistant_54")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a software bug triage assistant for the Conductor workflow "
                + "orchestration engine (https://github.com/conductor-oss/conductor).\n\n"
                + "Your capabilities:\n"
                + "1. Search and manage internal bug tickets (search_tickets, create_ticket, update_ticket)\n"
                + "2. Research Conductor issues using the search_agent tool\n"
                + "3. Look up real GitHub issues and PRs using the GitHub MCP tools\n"
                + "4. Cross-reference GitHub issues with internal tickets\n\n"
                + "When triaging: fetch the latest issues from GitHub, cross-reference with internal "
                + "tickets, research unfamiliar issues, and suggest next steps.")
            .tools(allTools)
            .build();

        AgentResult result = Agentspan.run(assistant,
            "Review our open tickets. Research the TaskStatusListener issue and suggest "
            + "what should be prioritized first.");
        result.printResult();

        Agentspan.shutdown();
    }
}
