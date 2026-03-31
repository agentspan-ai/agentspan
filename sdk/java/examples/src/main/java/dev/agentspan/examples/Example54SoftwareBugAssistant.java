// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.AgentTool;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Example 54 — Software Bug Assistant
 *
 * <p>Demonstrates {@link AgentTool#from(Agent)} for bug triage using:
 * <ul>
 *   <li>A search sub-agent (wrapped via {@code AgentTool.from()}) that researches issues</li>
 *   <li>Local ticket CRUD tools (search, create, update)</li>
 * </ul>
 *
 * <pre>
 * software_assistant
 *   tools:
 *     - AgentTool.from(search_agent)  ← researches technical issues
 *     - search_tickets                ← queries in-memory tracker
 *     - create_ticket                 ← opens new ticket
 *     - update_ticket                 ← changes status/priority
 * </pre>
 */
public class Example54SoftwareBugAssistant {

    // ── In-memory ticket store ────────────────────────────────────────────

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

    // ── Search sub-agent tools ────────────────────────────────────────────

    static class SearchTools {
        @Tool(name = "search_web_54", description = "Search for information about a Conductor bug or workflow issue")
        public Map<String, Object> searchWeb(String query) {
            Map<String, Map<String, Object>> results = Map.of(
                "task status listener", Map.of(
                    "source", "Conductor Docs",
                    "answer", "TaskStatusListener is only wired for SIMPLE tasks. System tasks " +
                              "like HTTP, INLINE, SUB_WORKFLOW bypass the listener because they " +
                              "complete synchronously within the decider loop."
                ),
                "do_while", Map.of(
                    "source", "GitHub PR #820",
                    "answer", "DO_WHILE tasks with 'items' now pass validation without loopCondition. " +
                              "Fixed in PR #820."
                ),
                "event handler fail", Map.of(
                    "source", "GitHub Issue #858",
                    "answer", "Event handlers with action: fail_task cannot set reasonForIncompletion. " +
                              "A proposed fix adds an optional 'reason' field."
                ),
                "workflow def", Map.of(
                    "source", "GitHub Issue #781",
                    "answer", "The /metadata/workflow endpoint returns all versions of all workflows " +
                              "causing slow UI loads. A pagination API for latest-versions is proposed."
                )
            );
            String q = query.toLowerCase();
            for (Map.Entry<String, Map<String, Object>> e : results.entrySet()) {
                if (q.contains(e.getKey())) {
                    Map<String, Object> r = new LinkedHashMap<>(e.getValue());
                    r.put("query", query);
                    r.put("found", true);
                    return r;
                }
            }
            return Map.of("query", query, "found", false, "summary", "No specific results found.");
        }
    }

    // ── Ticket management tools ───────────────────────────────────────────

    static class TicketTools {
        @Tool(name = "search_tickets_54", description = "Search the internal bug ticket database")
        public Map<String, Object> searchTickets(String query) {
            String q = query.toLowerCase();
            List<Map<String, Object>> matches = new ArrayList<>();
            for (Map<String, Object> t : TICKETS.values()) {
                String title = t.getOrDefault("title", "").toString().toLowerCase();
                if (title.contains(q) || q.contains("all") || q.contains("open")) {
                    matches.add(t);
                }
            }
            return Map.of("query", query, "count", matches.size(), "tickets", matches);
        }

        @Tool(name = "create_ticket_54", description = "Create a new bug ticket")
        public Map<String, Object> createTicket(String title, String description, String priority) {
            String id = "COND-" + String.format("%03d", NEXT_ID.getAndIncrement());
            Map<String, Object> t = ticket(id, title, "open",
                priority != null ? priority : "medium", LocalDate.now().toString());
            t.put("description", description);
            TICKETS.put(id, t);
            return Map.of("created", true, "ticket", t);
        }

        @Tool(name = "update_ticket_54", description = "Update an existing bug ticket status or priority")
        public Map<String, Object> updateTicket(String ticketId, String status, String priority) {
            Map<String, Object> t = TICKETS.get(ticketId.toUpperCase());
            if (t == null) return Map.of("error", "Ticket " + ticketId + " not found");
            if (status != null && !status.isEmpty()) t.put("status", status);
            if (priority != null && !priority.isEmpty()) t.put("priority", priority);
            return Map.of("updated", true, "ticket", t);
        }
    }

    public static void main(String[] args) {
        // Search sub-agent
        List<ToolDef> searchTools = ToolRegistry.fromInstance(new SearchTools());
        Agent searchAgent = Agent.builder()
            .name("search_agent_54")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a technical search assistant specializing in Conductor workflow " +
                "orchestration. Use search_web_54 to find relevant information about bugs. " +
                "Provide concise, actionable answers.")
            .tools(searchTools)
            .build();

        // Root agent: search sub-agent as a tool + ticket CRUD
        List<ToolDef> ticketTools = ToolRegistry.fromInstance(new TicketTools());
        List<ToolDef> allTools = new ArrayList<>();
        allTools.add(AgentTool.from(searchAgent));
        allTools.addAll(ticketTools);

        Agent assistant = Agent.builder()
            .name("software_assistant_54")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a software bug triage assistant for Conductor workflow orchestration.\n" +
                "Your capabilities:\n" +
                "1. Search and manage internal bug tickets (search_tickets_54, create_ticket_54, update_ticket_54)\n" +
                "2. Research Conductor issues using the search_agent_54 tool\n\n" +
                "When triaging: search existing tickets, research unfamiliar issues, " +
                "and suggest next steps.")
            .tools(allTools)
            .build();

        AgentResult result = Agentspan.run(assistant,
            "Review our open tickets. Research the TaskStatusListener issue and suggest " +
            "what should be prioritized first.");
        result.printResult();

        Agentspan.shutdown();
    }
}
