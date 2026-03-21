/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import dev.agentspan.runtime.model.AgentExecutionDetail;
import dev.agentspan.runtime.model.AgentRun;
import dev.agentspan.runtime.model.AgentSummary;
import dev.agentspan.runtime.model.CompileResponse;
import dev.agentspan.runtime.model.CreateTrackingWorkflowRequest;
import dev.agentspan.runtime.model.CreateTrackingWorkflowResponse;
import dev.agentspan.runtime.model.InjectTaskRequest;
import dev.agentspan.runtime.model.InjectTaskResponse;
import dev.agentspan.runtime.model.StartRequest;
import dev.agentspan.runtime.model.StartResponse;
import dev.agentspan.runtime.service.AgentDagService;
import dev.agentspan.runtime.service.AgentService;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import lombok.RequiredArgsConstructor;

import java.util.List;
import java.util.Map;

@Component
@RestController
@RequestMapping({"/api/agent"})
@RequiredArgsConstructor
public class AgentController {

    private final AgentService agentService;
    private final AgentDagService agentDagService;

    @GetMapping
    public String hello() {
        return "Hello, Agent!";
    }

    /**
     * Compile an agent configuration into a Conductor workflow definition.
     * Does not register or execute — useful for inspecting the compiled workflow.
     *
     * <p>Accepts either a native {@code AgentConfig} (as before) or a framework-specific
     * config via {@code StartRequest} with {@code framework} + {@code rawConfig} fields.</p>
     */
    @PostMapping("/compile")
    public CompileResponse compileAgent(@RequestBody StartRequest request) {
        return agentService.compile(request);
    }

    /**
     * Compile and register an agent workflow + task definitions without starting execution.
     * This is a CI/CD operation — the workflow is registered on the server and can be
     * triggered later via {@code /start} or by name through the Conductor API.
     */
    @PostMapping("/deploy")
    public StartResponse deployAgent(@RequestBody StartRequest request) {
        return agentService.deploy(request);
    }

    /**
     * Compile, register, and start an agent workflow execution.
     * Returns the workflow ID and name for tracking.
     */
    @PostMapping("/start")
    public StartResponse startAgent(@RequestBody StartRequest request) {
        return agentService.start(request);
    }

    /**
     * Open an SSE event stream for a running workflow.
     * Events include: thinking, tool_call, tool_result, guardrail_pass/fail,
     * waiting (HITL), handoff, error, done.
     *
     * <p>Supports reconnection via {@code Last-Event-ID} header — missed
     * events are replayed from an in-memory buffer.</p>
     */
    @GetMapping(value = "/stream/{workflowId}")
    public SseEmitter streamAgent(
            @PathVariable String workflowId,
            @RequestHeader(value = "Last-Event-ID", required = false) Long lastEventId) {
        return agentService.openStream(workflowId, lastEventId);
    }

    /**
     * Respond to a pending HITL (human-in-the-loop) task.
     * Use when a {@code waiting} SSE event is received.
     *
     * <p>Body examples:
     * <ul>
     *   <li>Approve: {@code {"approved": true}}</li>
     *   <li>Reject: {@code {"approved": false, "reason": "..."}}</li>
     *   <li>Message: {@code {"message": "..."}}</li>
     * </ul></p>
     */
    @PostMapping("/{workflowId}/respond")
    public void respondToAgent(
            @PathVariable String workflowId,
            @RequestBody Map<String, Object> output) {
        agentService.respond(workflowId, output);
    }

    /**
     * Receive an SSE event pushed by a framework worker (LangGraph/LangChain).
     * Always returns 200 — unknown workflowIds are silently dropped.
     */
    @PostMapping("/events/{workflowId}")
    public void pushFrameworkEvent(
            @PathVariable String workflowId,
            @RequestBody Map<String, Object> event) {
        agentService.pushFrameworkEvent(workflowId, event);
    }

    /**
     * List all registered agents (workflow defs with agent_sdk metadata).
     */
    @GetMapping("/list")
    public List<AgentSummary> listAgents() {
        return agentService.listAgents();
    }

    /**
     * Search agent executions with optional filters.
     */
    @GetMapping("/executions")
    public Map<String, Object> searchAgentExecutions(
            @RequestParam(defaultValue = "0") int start,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = "startTime:DESC") String sort,
            @RequestParam(required = false) String freeText,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String agentName,
            @RequestParam(required = false) String sessionId) {
        return agentService.searchAgentExecutions(start, size, sort, freeText, status, agentName, sessionId);
    }

    @GetMapping("/{name}")
    public Map<String, Object> getAgentDef(
            @PathVariable String name,
            @RequestParam(required = false) Integer version) {
        return agentService.getAgentDef(name, version);
    }

    @DeleteMapping("/{name}")
    public void deleteAgent(
            @PathVariable String name,
            @RequestParam(required = false) Integer version) {
        agentService.deleteAgent(name, version);
    }

    /**
     * Get detailed execution status for a single agent execution.
     */
    @GetMapping("/executions/{executionId}")
    public AgentExecutionDetail getExecutionDetail(@PathVariable String executionId) {
        return agentService.getExecutionDetail(executionId);
    }

    /**
     * Get the current status of a workflow execution.
     * Lightweight polling fallback when SSE is not available.
     */
    @GetMapping("/{workflowId}/status")
    public Map<String, Object> getAgentStatus(@PathVariable String workflowId) {
        return agentService.getStatus(workflowId);
    }

    /**
     * Get a workflow execution with its full task list.
     *
     * <p>Used by the SDK for token usage collection — returns task types,
     * output data (including token counts), and sub-workflow IDs for
     * recursive traversal into sub-agents.</p>
     */
    @GetMapping("/execution/{id}")
    public AgentRun getWorkflow(@PathVariable String id) {
        return agentService.getWorkflow(id);
    }

    /**
     * Inject a display-only task into a running workflow's task list.
     * Used by the SDK's DAG hook to record tool calls in the Conductor UI.
     * Writes directly to ExecutionDAO — does not trigger decide().
     */
    @PostMapping("/{workflowId}/tasks")
    public InjectTaskResponse injectTask(
            @PathVariable String workflowId,
            @RequestBody InjectTaskRequest req) {
        return agentDagService.injectTask(workflowId, req);
    }

    /**
     * Create a bare tracking workflow for sub-agent display.
     * The workflow has no tasks in its definition; tasks are injected via injectTask.
     * Stays RUNNING permanently — completion is a future enhancement.
     *
     * Note: Spring MVC resolves static segments before dynamic ones,
     * so POST /api/agent/workflow does not conflict with GET /api/agent/{name}.
     */
    @PostMapping("/workflow")
    public CreateTrackingWorkflowResponse createTrackingWorkflow(
            @RequestBody CreateTrackingWorkflowRequest req) {
        return agentDagService.createTrackingWorkflow(req);
    }
}
