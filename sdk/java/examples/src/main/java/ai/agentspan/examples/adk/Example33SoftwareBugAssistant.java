// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.AgentTool;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 33 — Software Bug Assistant
 *
 * <p>Java port of <code>sdk/python/examples/adk/33_software_bug_assistant.py</code>.
 *
 * <p>Demonstrates: native ADK {@link AgentTool} + local CRUD function tools
 * for bug triage. The Python source also uses an MCP tool for live GitHub
 * access; the Java port omits the MCP wiring (no Java MCP helper in scope)
 * and keeps a {@code search_web} sub-agent + local ticket store.
 *
 * <p>Did not port cleanly: {@code mcp_tool(server_url=...)} GitHub MCP
 * connector — there is no Java MCP factory in this SDK, so the GitHub
 * lookup capability is documented in instructions but not wired.
 */
public class Example33SoftwareBugAssistant {

    // ── In-memory ticket store (mirrors real conductor-oss/conductor issues) ──
    private static final Map<String, Map<String, Object>> TICKETS = new LinkedHashMap<>();
    private static int nextId = 4;

    static {
        Map<String, Object> t1 = new LinkedHashMap<>();
        t1.put("id", "COND-001");
        t1.put("title", "TaskStatusListener not invoked for system task lifecycle transitions");
        t1.put("status", "open");
        t1.put("priority", "high");
        t1.put("github_issue", 847);
        t1.put("description", "TaskStatusListener notifications are only fully wired for "
            + "worker tasks (SIMPLE/custom). Both synchronous and asynchronous "
            + "system tasks miss lifecycle transition callbacks.");
        t1.put("created", "2026-03-10");
        TICKETS.put("COND-001", t1);

        Map<String, Object> t2 = new LinkedHashMap<>();
        t2.put("id", "COND-002");
        t2.put("title", "Support reasonForIncompletion in fail_task event handlers");
        t2.put("status", "open");
        t2.put("priority", "medium");
        t2.put("github_issue", 858);
        t2.put("description", "When an event handler uses action: fail_task, there is no way "
            + "to set reasonForIncompletion. Need to support this field so "
            + "failed tasks have meaningful error messages.");
        t2.put("created", "2026-03-13");
        TICKETS.put("COND-002", t2);

        Map<String, Object> t3 = new LinkedHashMap<>();
        t3.put("id", "COND-003");
        t3.put("title", "Optimize /workflowDefs page: paginate latest-versions API");
        t3.put("status", "open");
        t3.put("priority", "medium");
        t3.put("github_issue", 781);
        t3.put("description", "The UI /workflowDefs page calls GET /metadata/workflow which "
            + "returns all versions of all workflows. This causes slow page "
            + "loads. Need pagination for the latest-versions endpoint.");
        t3.put("created", "2026-02-18");
        TICKETS.put("COND-003", t3);
    }

    // ── Ticket function tools ─────────────────────────────────────────────

    @Schema(description = "Get today's date.")
    public static Map<String, Object> getCurrentDate() {
        return Map.of("date", LocalDate.now().toString());
    }

    @Schema(description = "Search the internal bug ticket database for Conductor issues.")
    public static Map<String, Object> searchTickets(
            @Schema(name = "query", description = "Search query") String query) {
        String q = query.toLowerCase();
        List<Map<String, Object>> matches = new ArrayList<>();
        for (Map<String, Object> t : TICKETS.values()) {
            String title = ((String) t.get("title")).toLowerCase();
            String desc = ((String) t.get("description")).toLowerCase();
            if (title.contains(q) || desc.contains(q)) {
                matches.add(t);
            }
        }
        return Map.of("query", query, "count", matches.size(), "tickets", matches);
    }

    @Schema(description = "Create a new bug ticket in the internal tracker.")
    public static Map<String, Object> createTicket(
            @Schema(name = "title", description = "Ticket title") String title,
            @Schema(name = "description", description = "Ticket description") String description,
            @Schema(name = "priority", description = "Priority (low, medium, high)") String priority) {
        String ticketId = String.format("COND-%03d", nextId++);
        String p = priority == null || priority.isEmpty() ? "medium" : priority;
        Map<String, Object> ticket = new LinkedHashMap<>();
        ticket.put("id", ticketId);
        ticket.put("title", title);
        ticket.put("status", "open");
        ticket.put("priority", p);
        ticket.put("description", description);
        ticket.put("created", LocalDate.now().toString());
        TICKETS.put(ticketId, ticket);
        return Map.of("created", true, "ticket", ticket);
    }

    @Schema(description = "Update an existing bug ticket's status or priority.")
    public static Map<String, Object> updateTicket(
            @Schema(name = "ticket_id", description = "Ticket ID") String ticketId,
            @Schema(name = "status", description = "New status (optional)") String status,
            @Schema(name = "priority", description = "New priority (optional)") String priority) {
        Map<String, Object> ticket = TICKETS.get(ticketId.toUpperCase());
        if (ticket == null) {
            return Map.of("error", "Ticket " + ticketId + " not found");
        }
        if (status != null && !status.isEmpty()) {
            ticket.put("status", status);
        }
        if (priority != null && !priority.isEmpty()) {
            ticket.put("priority", priority);
        }
        return Map.of("updated", true, "ticket", ticket);
    }

    @Schema(description = "Search the web for information about a Conductor bug or workflow issue.")
    public static Map<String, Object> searchWeb(
            @Schema(name = "query", description = "Search query") String query) {
        Map<String, Map<String, Object>> results = new LinkedHashMap<>();
        results.put("task status listener", Map.of(
            "source", "Conductor Docs",
            "answer", "TaskStatusListener is only wired for SIMPLE tasks. System "
                + "tasks like HTTP, INLINE, SUB_WORKFLOW bypass the listener "
                + "because they complete synchronously within the decider loop."
        ));
        results.put("do_while loop", Map.of(
            "source", "GitHub PR #820",
            "answer", "DO_WHILE tasks with 'items' now pass validation without "
                + "loopCondition. Fixed in PR #820 — the validator was "
                + "unconditionally requiring loopCondition for all DO_WHILE tasks."
        ));
        results.put("event handler fail", Map.of(
            "source", "GitHub Issue #858",
            "answer", "Event handlers with action: fail_task cannot set "
                + "reasonForIncompletion. A proposed fix adds an optional "
                + "'reason' field to the fail_task action configuration."
        ));
        results.put("workflow def pagination", Map.of(
            "source", "GitHub Issue #781",
            "answer", "The /metadata/workflow endpoint returns all versions of all "
                + "workflows causing slow UI loads. A pagination API for "
                + "latest-versions is proposed to fix this."
        ));
        String q = query.toLowerCase();
        for (Map.Entry<String, Map<String, Object>> entry : results.entrySet()) {
            if (q.contains(entry.getKey())) {
                Map<String, Object> r = new LinkedHashMap<>();
                r.put("query", query);
                r.put("found", true);
                r.putAll(entry.getValue());
                return r;
            }
        }
        return Map.of("query", query, "found", false, "summary", "No specific results found.");
    }

    public static void main(String[] args) {
        LlmAgent searchAgent = LlmAgent.builder()
            .name("search_agent")
            .description("Technical search assistant for Conductor workflow orchestration issues.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a technical search assistant specializing in Conductor
                (conductor-oss/conductor) workflow orchestration. Use the search_web
                tool to find relevant information about bugs, errors, and Conductor
                configuration issues. Provide concise, actionable answers.
                """)
            .tools(FunctionTool.create(Example33SoftwareBugAssistant.class, "searchWeb"))
            .build();

        LlmAgent softwareAssistant = LlmAgent.builder()
            .name("software_assistant")
            .description("Triages Conductor bug tickets and cross-references them against known issues.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a software bug triage assistant for the Conductor workflow
                orchestration engine (https://github.com/conductor-oss/conductor).

                Your capabilities:
                1. Search and manage internal bug tickets (search_tickets, create_ticket, update_ticket)
                2. Research Conductor issues using the search_agent tool
                3. Cross-reference internal tickets against known issues

                When triaging:
                - Cross-reference with internal tickets (search_tickets)
                - Research any unfamiliar issues with the search_agent
                - Create internal tickets for new issues not yet tracked
                - Suggest next steps, referencing GitHub issue/PR numbers
                """)
            .tools(
                FunctionTool.create(Example33SoftwareBugAssistant.class, "getCurrentDate"),
                FunctionTool.create(Example33SoftwareBugAssistant.class, "searchTickets"),
                FunctionTool.create(Example33SoftwareBugAssistant.class, "createTicket"),
                FunctionTool.create(Example33SoftwareBugAssistant.class, "updateTicket"),
                AgentTool.create(searchAgent))
            .build();

        AgentResult result = Agentspan.run(softwareAssistant,
            "Review the latest open issues and PRs on conductor-oss/conductor. "
            + "Check if any of them relate to our internal tickets. "
            + "Pay attention to the DO_WHILE fix (PR #820) and the scheduler "
            + "persistence PRs. Give me a triage summary.");
        result.printResult();

        Agentspan.shutdown();
    }
}
