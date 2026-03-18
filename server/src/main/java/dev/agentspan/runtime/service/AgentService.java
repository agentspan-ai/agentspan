/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.common.metadata.tasks.TaskDef;
import com.netflix.conductor.common.metadata.workflow.StartWorkflowRequest;
import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.common.metadata.tasks.TaskResult;
import com.netflix.conductor.common.run.Workflow;
import com.netflix.conductor.core.execution.StartWorkflowInput;
import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.dao.MetadataDAO;
import com.netflix.conductor.service.ExecutionService;
import com.netflix.conductor.service.WorkflowService;

import com.netflix.conductor.common.run.SearchResult;
import com.netflix.conductor.common.run.WorkflowSummary;

import dev.agentspan.runtime.compiler.AgentCompiler;
import dev.agentspan.runtime.model.*;
import dev.agentspan.runtime.normalizer.NormalizerRegistry;
import dev.agentspan.runtime.util.ModelParser;
import dev.agentspan.runtime.util.ProviderValidator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import lombok.RequiredArgsConstructor;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import java.util.Optional;
import java.util.stream.Collectors;

@Component
@RequiredArgsConstructor
public class AgentService {

    private static final Logger log = LoggerFactory.getLogger(AgentService.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final AgentCompiler agentCompiler;
    private final NormalizerRegistry normalizerRegistry;
    private final MetadataDAO metadataDAO;
    private final WorkflowExecutor workflowExecutor;
    private final WorkflowService workflowService;
    private final AgentStreamRegistry streamRegistry;
    private final ExecutionService executionService;
    private final ProviderValidator providerValidator;

    /**
     * Compile an agent config into a WorkflowDef and return it.
     * Supports both native AgentConfig and framework-specific raw configs.
     */
    @SuppressWarnings("unchecked")
    public CompileResponse compile(StartRequest request) {
        AgentConfig config = resolveConfig(request);
        // Assign a default name for plan/compile if not provided
        if (config.getName() == null || config.getName().isEmpty()) {
            config.setName("agent_plan");
        }
        log.info("Compiling agent: {}", config.getName());
        WorkflowDef def = agentCompiler.compile(config);
        Map<String, Object> defMap = MAPPER.convertValue(def, Map.class);
        return CompileResponse.builder().workflowDef(defMap).build();
    }

    /**
     * Compile and register workflow + task definitions without starting execution.
     * This is a CI/CD operation — pushes the workflow to the server for later execution.
     */
    public StartResponse deploy(StartRequest request) {
        AgentConfig config = resolveConfig(request);
        log.info("Deploying agent: {}", config.getName());

        // 0. Pre-register child workflows for agent_tool types
        registerAgentToolWorkflows(config);

        // 1. Compile
        WorkflowDef def = agentCompiler.compile(config);

        // 1b. Stamp SDK metadata on the workflow definition
        String sdk = request.getFramework() != null ? request.getFramework() : "conductor";
        Map<String, Object> metadata = def.getMetadata() != null
                ? new LinkedHashMap<>(def.getMetadata()) : new LinkedHashMap<>();
        metadata.put("agent_sdk", sdk);
        def.setMetadata(metadata);

        // 2. Register workflow definition (upsert)
        metadataDAO.updateWorkflowDef(def);

        // 3. Register task definitions for worker tools
        registerTaskDefinitions(config);

        // Validate provider (warn only, don't terminate)
        validateModelProvider(config).ifPresent(err ->
            log.warn("Provider not configured for agent '{}': {}", config.getName(), err));

        return StartResponse.builder()
            .workflowName(def.getName())
            .build();
    }

    /**
     * Compile, register workflow + task definitions, and start execution.
     * Supports both native AgentConfig and framework-specific raw configs.
     */
    @SuppressWarnings("unchecked")
    public StartResponse start(StartRequest request) {
        AgentConfig config = resolveConfig(request);

        // Apply per-call timeout override from StartRequest
        if (request.getTimeoutSeconds() != null && request.getTimeoutSeconds() > 0) {
            config.setTimeoutSeconds(request.getTimeoutSeconds());
        }

        log.info("Starting agent: {}", config.getName());

        // 0. Pre-register child workflows for agent_tool types
        registerAgentToolWorkflows(config);

        // 1. Compile
        WorkflowDef def = agentCompiler.compile(config);

        // 1b. Stamp SDK metadata on the workflow definition
        String sdk = request.getFramework() != null ? request.getFramework() : "conductor";
        Map<String, Object> metadata = def.getMetadata() != null
                ? new LinkedHashMap<>(def.getMetadata()) : new LinkedHashMap<>();
        metadata.put("agent_sdk", sdk);
        def.setMetadata(metadata);

        // 2. Register workflow definition (upsert)
        metadataDAO.updateWorkflowDef(def);

        // 3. Register task definitions for worker tools
        registerTaskDefinitions(config);

        // 4. Start workflow execution
        StartWorkflowRequest startReq = new StartWorkflowRequest();
        startReq.setName(def.getName());
        startReq.setVersion(def.getVersion());
        startReq.setWorkflowDef(def);

        Map<String, Object> input = new LinkedHashMap<>();
        input.put("prompt", request.getPrompt());
        input.put("media", request.getMedia() != null ? request.getMedia() : List.of());
        input.put("session_id", request.getSessionId() != null ? request.getSessionId() : "");
        startReq.setInput(input);

        // Idempotency: use the key as correlationId and check for existing executions
        if (request.getIdempotencyKey() != null && !request.getIdempotencyKey().isEmpty()) {
            startReq.setCorrelationId(request.getIdempotencyKey());
            String existing = findExistingExecution(def.getName(), request.getIdempotencyKey());
            if (existing != null) {
                log.info("Idempotent hit: returning existing workflow {} for key '{}'",
                        existing, request.getIdempotencyKey());
                return StartResponse.builder()
                    .workflowId(existing)
                    .workflowName(def.getName())
                    .build();
            }
        }

        String workflowId = workflowExecutor.startWorkflow(new StartWorkflowInput(startReq));
        log.info("Started workflow: {} (id={})", def.getName(), workflowId);

        // Validate provider AFTER start — workflow is captured for replay
        Optional<String> validationError = validateModelProvider(config);
        if (validationError.isPresent()) {
            log.warn("Provider not configured for agent '{}': {}", config.getName(), validationError.get());
            workflowService.terminateWorkflow(workflowId, validationError.get());
        }

        return StartResponse.builder()
            .workflowId(workflowId)
            .workflowName(def.getName())
            .build();
    }

    // ── Agent discovery ─────────────────────────────────────────────

    /**
     * List all registered agents (workflow defs with agent_sdk metadata).
     */
    @SuppressWarnings("unchecked")
    public List<AgentSummary> listAgents() {
        List<WorkflowDef> allDefs = metadataDAO.getAllWorkflowDefsLatestVersions();
        List<AgentSummary> agents = new ArrayList<>();

        for (WorkflowDef def : allDefs) {
            Map<String, Object> metadata = def.getMetadata();
            if (metadata == null || !metadata.containsKey("agent_sdk")) {
                continue;
            }

            String checksum;
            try {
                String json = MAPPER.writeValueAsString(def);
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                byte[] hash = digest.digest(json.getBytes(StandardCharsets.UTF_8));
                StringBuilder hex = new StringBuilder();
                for (byte b : hash) {
                    hex.append(String.format("%02x", b));
                }
                checksum = hex.toString();
            } catch (Exception e) {
                log.warn("Failed to compute checksum for workflow {}", def.getName(), e);
                checksum = null;
            }

            List<String> tags = null;
            Object caps = metadata.get("agent_capabilities");
            if (caps instanceof List) {
                tags = (List<String>) caps;
            }

            agents.add(AgentSummary.builder()
                    .name(def.getName())
                    .version(def.getVersion())
                    .type((String) metadata.get("agent_sdk"))
                    .tags(tags)
                    .createTime(def.getCreateTime())
                    .updateTime(def.getUpdateTime())
                    .description(def.getDescription())
                    .checksum(checksum)
                    .build());
        }

        return agents;
    }

    /**
     * Search agent executions with optional filters.
     */
    public Map<String, Object> searchAgentExecutions(int start, int size, String sort,
                                                      String freeText, String status,
                                                      String agentName, String sessionId) {
        // Determine which workflow types to query
        List<String> workflowNames;
        if (agentName != null && !agentName.isEmpty()) {
            workflowNames = List.of(agentName);
        } else {
            workflowNames = listAgents().stream()
                    .map(AgentSummary::getName)
                    .collect(Collectors.toList());
        }

        if (workflowNames.isEmpty()) {
            Map<String, Object> empty = new LinkedHashMap<>();
            empty.put("totalHits", 0L);
            empty.put("results", List.of());
            return empty;
        }

        // Build query string
        String nameList = workflowNames.stream()
                .map(n -> "'" + n + "'")
                .collect(Collectors.joining(","));
        StringBuilder query = new StringBuilder("workflowType IN (").append(nameList).append(")");
        if (status != null && !status.isEmpty()) {
            query.append(" AND status = '").append(status).append("'");
        }

        // Use sessionId as freeText search if provided
        String searchText = freeText != null ? freeText : "*";
        if (sessionId != null && !sessionId.isEmpty()) {
            searchText = sessionId;
        }

        SearchResult<WorkflowSummary> searchResult = workflowService.searchWorkflows(
                start, size, sort, searchText, query.toString());

        List<AgentExecutionSummary> results = searchResult.getResults().stream()
                .map(ws -> AgentExecutionSummary.builder()
                        .workflowId(ws.getWorkflowId())
                        .agentName(ws.getWorkflowType())
                        .version(ws.getVersion())
                        .status(ws.getStatus() != null ? ws.getStatus().name() : null)
                        .startTime(ws.getStartTime())
                        .endTime(ws.getEndTime())
                        .updateTime(ws.getUpdateTime())
                        .executionTime(ws.getExecutionTime())
                        .input(ws.getInput())
                        .output(ws.getOutput())
                        .createdBy(ws.getCreatedBy())
                        .build())
                .collect(Collectors.toList());

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("totalHits", searchResult.getTotalHits());
        response.put("results", results);
        return response;
    }

    /**
     * Get detailed execution status for a single agent execution.
     */
    public AgentExecutionDetail getExecutionDetail(String executionId) {
        Workflow workflow = executionService.getExecutionStatus(executionId, true);

        // Find the last non-terminal task as the "current" task
        AgentExecutionDetail.CurrentTask currentTask = null;
        List<Task> tasks = workflow.getTasks();
        for (int i = tasks.size() - 1; i >= 0; i--) {
            Task task = tasks.get(i);
            if (!task.getStatus().isTerminal()) {
                currentTask = AgentExecutionDetail.CurrentTask.builder()
                        .taskRefName(task.getReferenceTaskName())
                        .taskType(task.getTaskType())
                        .status(task.getStatus().name())
                        .inputData(task.getInputData())
                        .outputData(task.getOutputData())
                        .build();
                break;
            }
        }

        return AgentExecutionDetail.builder()
                .workflowId(executionId)
                .agentName(workflow.getWorkflowName())
                .version(workflow.getWorkflowVersion())
                .status(workflow.getStatus().name())
                .input(workflow.getInput())
                .output(workflow.getOutput())
                .currentTask(currentTask)
                .build();
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getAgentDef(String name, Integer version) {
        WorkflowDef def;
        if (version != null) {
            def = metadataDAO.getWorkflowDef(name, version)
                    .orElseThrow(() -> new IllegalArgumentException("Agent not found: " + name + " v" + version));
        } else {
            def = metadataDAO.getLatestWorkflowDef(name)
                    .orElseThrow(() -> new IllegalArgumentException("Agent not found: " + name));
        }
        return MAPPER.convertValue(def, Map.class);
    }

    public void deleteAgent(String name, Integer version) {
        if (version != null) {
            metadataDAO.removeWorkflowDef(name, version);
        } else {
            // Remove latest version
            WorkflowDef def = metadataDAO.getLatestWorkflowDef(name)
                    .orElseThrow(() -> new IllegalArgumentException("Agent not found: " + name));
            metadataDAO.removeWorkflowDef(name, def.getVersion());
        }
    }

    /**
     * Search for an existing workflow with the given correlationId (idempotency key).
     * Returns the workflow ID if a RUNNING or COMPLETED execution exists, null otherwise.
     */
    private String findExistingExecution(String workflowName, String idempotencyKey) {
        try {
            String query = "workflowType = '" + workflowName + "' AND status IN ('RUNNING', 'COMPLETED')";
            SearchResult<WorkflowSummary> results = workflowService.searchWorkflows(
                    0, 1, "startTime:DESC", idempotencyKey, query);
            if (results.getTotalHits() > 0) {
                WorkflowSummary match = results.getResults().get(0);
                if (idempotencyKey.equals(match.getCorrelationId())) {
                    return match.getWorkflowId();
                }
            }
        } catch (Exception e) {
            log.debug("Idempotency check failed for key '{}': {}", idempotencyKey, e.getMessage());
        }
        return null;
    }

    /**
     * Walk the agent tree and register task definitions for all worker tools.
     */
    private void registerTaskDefinitions(AgentConfig config) {
        Set<String> registered = new HashSet<>();
        collectAndRegisterTasks(config, registered);
    }

    private void collectAndRegisterTasks(AgentConfig config, Set<String> registered) {
        // Register dispatch task for this agent's tools
        if (config.getTools() != null) {
            for (ToolConfig tool : config.getTools()) {
                if ("worker".equals(tool.getToolType()) && !registered.contains(tool.getName())) {
                    registerTaskDef(tool.getName());
                    registered.add(tool.getName());
                }
            }
        }

        // Register stop_when worker
        if (config.getStopWhen() != null && config.getStopWhen().getTaskName() != null) {
            String taskName = config.getStopWhen().getTaskName();
            if (!registered.contains(taskName)) {
                registerTaskDef(taskName);
                registered.add(taskName);
            }
        }

        // Register custom guardrail workers
        if (config.getGuardrails() != null) {
            for (GuardrailConfig g : config.getGuardrails()) {
                if ("custom".equals(g.getGuardrailType()) && g.getTaskName() != null) {
                    if (!registered.contains(g.getTaskName())) {
                        registerTaskDef(g.getTaskName());
                        registered.add(g.getTaskName());
                    }
                }
            }
        }

        // Register callback workers
        if (config.getCallbacks() != null) {
            for (CallbackConfig cb : config.getCallbacks()) {
                if (cb.getTaskName() != null && !registered.contains(cb.getTaskName())) {
                    registerTaskDef(cb.getTaskName());
                    registered.add(cb.getTaskName());
                }
            }
        }

        // Register handoff check worker for swarm
        if (config.getHandoffs() != null && !config.getHandoffs().isEmpty()) {
            String taskName = config.getName() + "_handoff_check";
            if (!registered.contains(taskName)) {
                registerTaskDef(taskName);
                registered.add(taskName);
            }
        }

        // Register process_selection worker for manual
        if ("manual".equals(config.getStrategy())) {
            String taskName = config.getName() + "_process_selection";
            if (!registered.contains(taskName)) {
                registerTaskDef(taskName);
                registered.add(taskName);
            }
        }

        // Register check_transfer worker for hybrid
        if (config.getAgents() != null && !config.getAgents().isEmpty() &&
            config.getTools() != null && !config.getTools().isEmpty()) {
            String taskName = config.getName() + "_check_transfer";
            if (!registered.contains(taskName)) {
                registerTaskDef(taskName);
                registered.add(taskName);
            }
        }

        // Recurse into sub-agents
        if (config.getAgents() != null) {
            for (AgentConfig sub : config.getAgents()) {
                if (!sub.isExternal()) {
                    collectAndRegisterTasks(sub, registered);
                }
            }
        }
    }

    // ── Agent-as-tool workflow registration ──────────────────────

    /**
     * Pre-register child agent workflows for any agent_tool type tools.
     * Called before compilation so the enrichment script can reference
     * the child workflow by name.
     */
    @SuppressWarnings("unchecked")
    private void registerAgentToolWorkflows(AgentConfig config) {
        if (config.getTools() != null) {
            for (ToolConfig tool : config.getTools()) {
                if (!"agent_tool".equals(tool.getToolType()) || tool.getConfig() == null) {
                    continue;
                }

                Object agentConfigObj = tool.getConfig().get("agentConfig");
                if (agentConfigObj == null) continue;

                // Convert the AgentConfig (or LinkedHashMap from Jackson) to AgentConfig
                AgentConfig childConfig;
                if (agentConfigObj instanceof AgentConfig) {
                    childConfig = (AgentConfig) agentConfigObj;
                } else if (agentConfigObj instanceof Map) {
                    childConfig = MAPPER.convertValue(agentConfigObj, AgentConfig.class);
                } else {
                    log.warn("Unexpected agentConfig type for tool '{}': {}",
                            tool.getName(), agentConfigObj.getClass());
                    continue;
                }

                // Recursively register any nested agent_tool workflows
                registerAgentToolWorkflows(childConfig);

                // Compile and register the child agent workflow
                WorkflowDef childDef = agentCompiler.compile(childConfig);
                metadataDAO.updateWorkflowDef(childDef);
                log.info("Registered agent_tool child workflow: {} for tool '{}'",
                        childDef.getName(), tool.getName());

                // Register task definitions for the child's worker tools
                registerTaskDefinitions(childConfig);

                // Store the workflow name back so the enrichment script can reference it
                tool.getConfig().put("workflowName", childDef.getName());
            }
        }

        // Also recurse into sub-agents (they might have agent_tool tools too)
        if (config.getAgents() != null) {
            for (AgentConfig sub : config.getAgents()) {
                if (!sub.isExternal()) {
                    registerAgentToolWorkflows(sub);
                }
            }
        }
    }

    // ── Provider validation ─────────────────────────────────────────

    private Optional<String> validateModelProvider(AgentConfig config) {
        if (config.getModel() != null && !config.getModel().isBlank()) {
            ModelParser.ParsedModel parsed = ModelParser.parse(config.getModel());
            Optional<String> error = providerValidator.validateProvider(parsed.getProvider());
            if (error.isPresent()) return error;
        }
        if (config.getAgents() != null) {
            for (AgentConfig sub : config.getAgents()) {
                if (!sub.isExternal()) {
                    Optional<String> error = validateModelProvider(sub);
                    if (error.isPresent()) return error;
                }
            }
        }
        return Optional.empty();
    }

    // ── Config resolution ─────────────────────────────────────────

    /**
     * Resolve the AgentConfig from a StartRequest.
     * If {@code framework} is set, normalize the raw config via the appropriate normalizer.
     * Otherwise, use the native {@code agentConfig} field directly.
     */
    private AgentConfig resolveConfig(StartRequest request) {
        if (request.getFramework() != null && !request.getFramework().isEmpty()) {
            log.info("Normalizing framework '{}' agent config", request.getFramework());
            return normalizerRegistry.normalize(request.getFramework(), request.getRawConfig());
        }
        return request.getAgentConfig();
    }

    // ── SSE Streaming ──────────────────────────────────────────────

    /**
     * Open an SSE stream for a workflow. Replays missed events on reconnect.
     */
    public SseEmitter openStream(String workflowId, Long lastEventId) {
        log.info("Opening SSE stream for workflow {} (lastEventId={})", workflowId, lastEventId);
        return streamRegistry.register(workflowId, lastEventId);
    }

    /**
     * Respond to a pending HITL task in a workflow.
     */
    public void respond(String workflowId, Map<String, Object> output) {
        log.info("Responding to workflow {}: {}", workflowId, output);

        // Find the pending task (HUMAN type, IN_PROGRESS status)
        Workflow workflow = executionService.getExecutionStatus(workflowId, true);
        Task pendingTask = null;
        for (Task task : workflow.getTasks()) {
            if ("HUMAN".equals(task.getTaskType())
                    && task.getStatus() == Task.Status.IN_PROGRESS) {
                pendingTask = task;
                break;
            }
        }

        if (pendingTask == null) {
            throw new IllegalStateException(
                    "No pending HUMAN task found in workflow " + workflowId);
        }

        // Update the task with the human's response
        TaskResult taskResult = new TaskResult();
        taskResult.setTaskId(pendingTask.getTaskId());
        taskResult.setWorkflowInstanceId(workflowId);
        taskResult.setStatus(TaskResult.Status.COMPLETED);
        Map<String, Object> outputData = new LinkedHashMap<>(
                pendingTask.getOutputData() != null ? pendingTask.getOutputData() : Map.of());
        outputData.putAll(output);
        taskResult.setOutputData(outputData);
        executionService.updateTask(taskResult);
        log.info("Completed HUMAN task {} in workflow {}", pendingTask.getReferenceTaskName(), workflowId);
    }

    /**
     * Get the current status of a workflow.
     */
    public Map<String, Object> getStatus(String workflowId) {
        Workflow workflow = executionService.getExecutionStatus(workflowId, true);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("workflowId", workflowId);
        result.put("status", workflow.getStatus().name());

        boolean isComplete = workflow.getStatus().isTerminal();
        result.put("isComplete", isComplete);
        result.put("isRunning", workflow.getStatus() == Workflow.WorkflowStatus.RUNNING);

        if (isComplete) {
            result.put("output", workflow.getOutput());
        }

        String reason = workflow.getReasonForIncompletion();
        if (reason != null && !reason.isBlank()) {
            result.put("reasonForIncompletion", reason);
        }

        // Find pending HUMAN task
        for (Task task : workflow.getTasks()) {
            if ("HUMAN".equals(task.getTaskType())
                    && task.getStatus() == Task.Status.IN_PROGRESS) {
                Map<String, Object> pendingTool = new LinkedHashMap<>();
                pendingTool.put("taskRefName", task.getReferenceTaskName());
                if (task.getInputData() != null) {
                    pendingTool.put("tool_name", task.getInputData().get("tool_name"));
                    pendingTool.put("parameters", task.getInputData().get("parameters"));
                }
                result.put("pendingTool", pendingTool);
                result.put("isWaiting", true);
                break;
            }
        }

        return result;
    }

    // ── Task registration ────────────────────────────────────────────

    private void registerTaskDef(String taskName) {
        TaskDef taskDef = new TaskDef();
        taskDef.setName(taskName);
        taskDef.setRetryCount(2);
        taskDef.setRetryDelaySeconds(2);
        taskDef.setRetryLogic(TaskDef.RetryLogic.LINEAR_BACKOFF);
        taskDef.setTimeoutSeconds(120);
        taskDef.setResponseTimeoutSeconds(120);
        taskDef.setTimeoutPolicy(TaskDef.TimeoutPolicy.RETRY);

        try {
            TaskDef existing = metadataDAO.getTaskDef(taskName);
            if (existing != null) {
                metadataDAO.updateTaskDef(taskDef);
                log.debug("Updated task definition: {}", taskName);
                return;
            }
        } catch (Exception e) {
            // Task doesn't exist, create it
        }

        metadataDAO.createTaskDef(taskDef);
        log.info("Registered task definition: {}", taskName);
    }
}
