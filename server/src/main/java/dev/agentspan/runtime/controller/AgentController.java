/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.common.metadata.tasks.TaskExecLog;
import com.netflix.conductor.common.metadata.tasks.TaskResult;
import com.netflix.conductor.common.metadata.workflow.RerunWorkflowRequest;
import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.common.run.SearchResult;
import com.netflix.conductor.common.run.Workflow;
import com.netflix.conductor.common.run.WorkflowSummary;

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
import dev.agentspan.runtime.model.TaskListResponse;
import dev.agentspan.runtime.service.AgentDagService;
import dev.agentspan.runtime.service.AgentService;

import lombok.RequiredArgsConstructor;

@Component
@RestController
@RequestMapping({"/api/agent"})
@RequiredArgsConstructor
public class AgentController {

    private final AgentService agentService;
    private final AgentDagService agentDagService;

    /**
     * Compile an agent configuration into an execution plan.
     * Does not register or execute — useful for inspecting the compiled definition.
     *
     * <p>Accepts either a native {@code AgentConfig} or a framework-specific
     * config via {@code StartRequest} with {@code framework} + {@code rawConfig} fields.</p>
     */
    @PostMapping("/compile")
    public CompileResponse compileAgent(@RequestBody StartRequest request) {
        return agentService.compile(request);
    }

    /**
     * Compile and register an agent definition without starting execution.
     * This is a CI/CD operation — the agent is registered on the server and can be
     * triggered later via {@code /start} or by name.
     */
    @PostMapping("/deploy")
    public StartResponse deployAgent(@RequestBody StartRequest request) {
        return agentService.deploy(request);
    }

    /**
     * Compile, register, and start an agent execution.
     * Returns the execution ID and agent name for tracking.
     */
    @PostMapping("/start")
    public StartResponse startAgent(@RequestBody StartRequest request) {
        return agentService.start(request);
    }

    /**
     * Open an SSE event stream for a running agent execution.
     * Events include: thinking, tool_call, tool_result, guardrail_pass/fail,
     * waiting (HITL), handoff, error, done.
     *
     * <p>Supports reconnection via {@code Last-Event-ID} header — missed
     * events are replayed from an in-memory buffer.</p>
     */
    @GetMapping(value = "/stream/{executionId}")
    public SseEmitter streamAgent(
            @PathVariable String executionId,
            @RequestHeader(value = "Last-Event-ID", required = false) Long lastEventId) {
        return agentService.openStream(executionId, lastEventId);
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
    @PostMapping("/{executionId}/respond")
    public void respondToAgent(@PathVariable String executionId, @RequestBody Map<String, Object> output) {
        agentService.respond(executionId, output);
    }

    /**
     * Receive an SSE event pushed by a framework worker (LangGraph/LangChain).
     * Always returns 200 — unknown execution IDs are silently dropped.
     */
    @PostMapping("/events/{executionId}")
    public void pushFrameworkEvent(@PathVariable String executionId, @RequestBody Map<String, Object> event) {
        agentService.pushFrameworkEvent(executionId, event);
    }

    /**
     * List all registered agents.
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
    public Map<String, Object> getAgentDef(@PathVariable String name, @RequestParam(required = false) Integer version) {
        return agentService.getAgentDef(name, version);
    }

    @DeleteMapping("/{name}")
    public void deleteAgent(@PathVariable String name, @RequestParam(required = false) Integer version) {
        agentService.deleteAgent(name, version);
    }

    /**
     * Get detailed execution status for a single agent execution.
     */
    @GetMapping("/executions/{executionId}")
    public AgentExecutionDetail getExecutionDetail(@PathVariable String executionId) {
        return agentService.getExecutionDetail(executionId);
    }

    /** Pause a running agent execution. */
    @PutMapping("/{executionId}/pause")
    public void pauseAgent(@PathVariable String executionId) {
        agentService.pauseAgent(executionId);
    }

    /** Resume a paused agent execution. */
    @PutMapping("/{executionId}/resume")
    public void resumeAgent(@PathVariable String executionId) {
        agentService.resumeAgent(executionId);
    }

    /** Cancel a running agent execution. */
    @DeleteMapping("/{executionId}/cancel")
    public void cancelAgent(@PathVariable String executionId, @RequestParam(required = false) String reason) {
        agentService.cancelAgent(executionId, reason);
    }

    /**
     * Get the current status of an agent execution.
     * Lightweight polling fallback when SSE is not available.
     */
    @GetMapping("/{executionId}/status")
    public Map<String, Object> getAgentStatus(@PathVariable String executionId) {
        return agentService.getStatus(executionId);
    }

    /**
     * Get an agent execution with its full task list.
     *
     * <p>Used by the SDK for token usage collection — returns task types,
     * output data (including token counts), and sub-workflow IDs for
     * recursive traversal into sub-agents.</p>
     */
    @GetMapping("/execution/{executionId}")
    public AgentRun getExecution(@PathVariable String executionId) {
        return agentService.getExecution(executionId);
    }

    /**
     * Inject a display-only task into a running execution's task list.
     * Used by the SDK's DAG hook to record tool calls in the UI.
     * Writes directly to ExecutionDAO — does not trigger decide().
     */
    @PostMapping("/{executionId}/tasks")
    public InjectTaskResponse injectTask(@PathVariable String executionId, @RequestBody InjectTaskRequest req) {
        return agentDagService.injectTask(executionId, req);
    }

    /**
     * Create a bare tracking execution for sub-agent display.
     * The execution has no tasks in its definition; tasks are injected via injectTask.
     */
    @PostMapping("/execution")
    public CreateTrackingWorkflowResponse createTrackingExecution(@RequestBody CreateTrackingWorkflowRequest req) {
        return agentDagService.createTrackingWorkflow(req);
    }

    /** Mark a tracking execution as COMPLETED. */
    @PostMapping("/execution/{executionId}/complete")
    public void completeTrackingExecution(
            @PathVariable String executionId,
            @RequestBody(required = false) Map<String, Object> output) {
        agentDagService.completeTrackingWorkflow(executionId, output);
    }

    // ── Execution lifecycle (UI) ────────────────────────────────────

    /** Get full execution with tasks (Conductor Workflow object, used by UI). */
    @GetMapping("/executions/{executionId}/full")
    public Workflow getFullExecution(@PathVariable String executionId) {
        return agentService.getFullExecution(executionId);
    }

    /** Restart a completed/failed execution. */
    @PostMapping("/executions/{executionId}/restart")
    public void restartExecution(
            @PathVariable String executionId, @RequestParam(defaultValue = "false") boolean useLatestDefinitions) {
        agentService.restartExecution(executionId, useLatestDefinitions);
    }

    /** Retry a failed execution from the failed task. */
    @PostMapping("/executions/{executionId}/retry")
    public void retryExecution(
            @PathVariable String executionId, @RequestParam(defaultValue = "false") boolean resumeSubworkflowTasks) {
        agentService.retryExecution(executionId, resumeSubworkflowTasks);
    }

    /** Rerun execution from a specific task. */
    @PostMapping("/executions/{executionId}/rerun")
    public String rerunExecution(@PathVariable String executionId, @RequestBody RerunWorkflowRequest request) {
        return agentService.rerunExecution(executionId, request);
    }

    /** Terminate a running execution (used by UI delete action). */
    @DeleteMapping("/executions/{executionId}")
    public void terminateExecution(@PathVariable String executionId, @RequestParam(required = false) String reason) {
        agentService.cancelAgent(executionId, reason);
    }

    /** Get paginated task list for an execution. */
    @GetMapping("/executions/{executionId}/tasks")
    public TaskListResponse getExecutionTasks(
            @PathVariable String executionId,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "15") int count,
            @RequestParam(defaultValue = "0") int start) {
        return agentService.getExecutionTasks(executionId, status, count, start);
    }

    /** Update a task's status within an execution. */
    @PostMapping("/tasks/{executionId}/{refTaskName}/{status}")
    public void updateTaskStatus(
            @PathVariable String executionId,
            @PathVariable String refTaskName,
            @PathVariable String status,
            @RequestParam(defaultValue = "agent-ui") String workerid,
            @RequestBody(required = false) Map<String, Object> body) {
        // Reuse existing task update logic
        Workflow wf = agentService.getFullExecution(executionId);
        Task task = wf.getTasks().stream()
                .filter(t -> refTaskName.equals(t.getReferenceTaskName()))
                .reduce((first, second) -> second)
                .orElseThrow(() ->
                        new com.netflix.conductor.core.exception.NotFoundException("Task not found: " + refTaskName));
        TaskResult taskResult = new TaskResult(task);
        taskResult.setStatus(TaskResult.Status.valueOf(status));
        taskResult.setWorkerId(workerid);
        if (body != null) {
            taskResult.setOutputData(body);
        }
        agentService.updateTaskResult(taskResult);
    }

    /** Get task logs. */
    @GetMapping("/tasks/{taskId}/log")
    public List<TaskExecLog> getTaskLogs(@PathVariable String taskId) {
        return agentService.getTaskLogs(taskId);
    }

    // ── Search ──────────────────────────────────────────────────────

    /** Search executions (pass-through to Conductor search, used by UI). */
    @GetMapping("/executions/search")
    public SearchResult<WorkflowSummary> searchExecutionsRaw(
            @RequestParam(defaultValue = "0") int start,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = "startTime:DESC") String sort,
            @RequestParam(required = false) String freeText,
            @RequestParam(required = false) String query) {
        return agentService.searchExecutionsRaw(start, size, sort, freeText, query);
    }

    // ── Bulk operations ─────────────────────────────────────────────

    @PutMapping("/executions/bulk/pause")
    public void bulkPause(@RequestBody List<String> ids) {
        ids.forEach(id -> agentService.pauseAgent(id));
    }

    @PutMapping("/executions/bulk/resume")
    public void bulkResume(@RequestBody List<String> ids) {
        ids.forEach(id -> agentService.resumeAgent(id));
    }

    @PostMapping("/executions/bulk/restart")
    public void bulkRestart(
            @RequestBody List<String> ids, @RequestParam(defaultValue = "false") boolean useLatestDefinitions) {
        ids.forEach(id -> agentService.restartExecution(id, useLatestDefinitions));
    }

    @PostMapping("/executions/bulk/retry")
    public void bulkRetry(@RequestBody List<String> ids) {
        ids.forEach(id -> agentService.retryExecution(id, false));
    }

    @PostMapping("/executions/bulk/terminate")
    public void bulkTerminate(@RequestBody List<String> ids, @RequestParam(required = false) String reason) {
        ids.forEach(id -> agentService.cancelAgent(id, reason));
    }

    // ── Definition metadata ─────────────────────────────────────────

    @GetMapping("/definitions/{name}")
    public WorkflowDef getAgentDefinition(@PathVariable String name, @RequestParam(required = false) Integer version) {
        return agentService.getAgentDefinition(name, version);
    }
}
