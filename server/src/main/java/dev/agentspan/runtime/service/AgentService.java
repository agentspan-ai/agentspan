/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.Optional;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.common.metadata.tasks.TaskDef;
import com.netflix.conductor.common.metadata.tasks.TaskExecLog;
import com.netflix.conductor.common.metadata.tasks.TaskResult;
import com.netflix.conductor.common.metadata.workflow.RerunWorkflowRequest;
import com.netflix.conductor.common.metadata.workflow.StartWorkflowRequest;
import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.common.metadata.workflow.WorkflowTask;
import com.netflix.conductor.common.run.SearchResult;
import com.netflix.conductor.common.run.Workflow;
import com.netflix.conductor.common.run.WorkflowSummary;
import com.netflix.conductor.core.execution.StartWorkflowInput;
import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.dao.MetadataDAO;
import com.netflix.conductor.service.ExecutionService;
import com.netflix.conductor.service.WorkflowService;

import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.auth.User;
import dev.agentspan.runtime.compiler.AgentCompiler;
import dev.agentspan.runtime.credentials.ExecutionTokenService;
import dev.agentspan.runtime.model.*;
import dev.agentspan.runtime.normalizer.NormalizerRegistry;
import dev.agentspan.runtime.util.ModelParser;
import dev.agentspan.runtime.util.ProviderValidator;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor(onConstructor_ = {@Autowired})
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

    @Autowired(required = false)
    private ExecutionTokenService executionTokenService;

    /** Package-private constructor for testing with ExecutionTokenService */
    AgentService(
            AgentCompiler agentCompiler,
            NormalizerRegistry normalizerRegistry,
            MetadataDAO metadataDAO,
            WorkflowExecutor workflowExecutor,
            WorkflowService workflowService,
            AgentStreamRegistry streamRegistry,
            ExecutionService executionService,
            ProviderValidator providerValidator,
            ExecutionTokenService executionTokenService) {
        this.agentCompiler = agentCompiler;
        this.normalizerRegistry = normalizerRegistry;
        this.metadataDAO = metadataDAO;
        this.workflowExecutor = workflowExecutor;
        this.workflowService = workflowService;
        this.streamRegistry = streamRegistry;
        this.executionService = executionService;
        this.providerValidator = providerValidator;
        this.executionTokenService = executionTokenService;
    }

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

        // Stamp agentDef into the compiled WorkflowDef so it is persisted when
        // the SDK passes the def inline to Conductor's start_workflow.
        String sdk = request.getFramework() != null ? request.getFramework() : "conductor";
        Map<String, Object> metadata =
                def.getMetadata() != null ? new LinkedHashMap<>(def.getMetadata()) : new LinkedHashMap<>();
        metadata.put("agent_sdk", sdk);
        stampAgentDef(metadata, request);
        def.setMetadata(metadata);

        Set<String> workerNames = collectSimpleTaskNames(def);
        collectDynamicTransferNames(config, workerNames);
        List<String> requiredWorkers = new ArrayList<>(workerNames);
        Map<String, Object> defMap = MAPPER.convertValue(def, Map.class);
        return CompileResponse.builder()
                .workflowDef(defMap)
                .requiredWorkers(requiredWorkers)
                .build();
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
        Map<String, Object> metadata =
                def.getMetadata() != null ? new LinkedHashMap<>(def.getMetadata()) : new LinkedHashMap<>();
        metadata.put("agent_sdk", sdk);
        stampAgentDef(metadata, request);
        def.setMetadata(metadata);

        // 2. Register workflow definition (upsert)
        metadataDAO.updateWorkflowDef(def);

        // 3. Register task definitions for worker tools
        registerTaskDefinitions(config);

        // Validate provider (warn only, don't terminate)
        validateModelProvider(config)
                .ifPresent(err -> log.warn("Provider not configured for agent '{}': {}", config.getName(), err));

        Set<String> deployWorkerNames = collectSimpleTaskNames(def);
        collectDynamicTransferNames(config, deployWorkerNames);
        return StartResponse.builder()
                .agentName(def.getName())
                .requiredWorkers(new ArrayList<>(deployWorkerNames))
                .build();
    }

    /**
     * Compile, register workflow + task definitions, and start execution.
     * Supports both native AgentConfig and framework-specific raw configs.
     */
    @SuppressWarnings("unchecked")
    public StartResponse start(StartRequest request) {
        validateStartInput(request);
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
        Map<String, Object> metadata =
                def.getMetadata() != null ? new LinkedHashMap<>(def.getMetadata()) : new LinkedHashMap<>();
        metadata.put("agent_sdk", sdk);
        stampAgentDef(metadata, request);
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
        input.put("context", request.getContext() != null ? request.getContext() : Map.of());
        input.put("session_id", request.getSessionId() != null ? request.getSessionId() : "");
        if (request.getCredentials() != null && !request.getCredentials().isEmpty()) {
            input.put("credentials", request.getCredentials());
        }
        // Extract cwd from rawConfig for frameworks that pass it
        String cwd = ".";
        if (request.getRawConfig() != null && request.getRawConfig().get("cwd") instanceof String rawCwd) {
            cwd = rawCwd;
        }
        input.put("cwd", cwd);

        // Mint execution token and embed in workflow variables for worker credential resolution
        if (executionTokenService != null) {
            try {
                long timeoutSeconds = config.getTimeoutSeconds() > 0 ? config.getTimeoutSeconds() : 0;
                List<String> declaredNames = extractDeclaredCredentials(config);
                // Also include credentials from the start request payload
                // (used by framework agents and run(credentials=[...]) calls)
                Object inputCreds = input.get("credentials");
                if (inputCreds instanceof List<?> credList) {
                    for (Object c : credList) {
                        if (c instanceof String s && !declaredNames.contains(s)) {
                            declaredNames.add(s);
                        }
                    }
                }
                User currentUser =
                        RequestContextHolder.get().map(ctx -> ctx.getUser()).orElse(null);
                if (currentUser != null) {
                    String token = executionTokenService.mint(
                            currentUser.getId(), null /* executionId not known yet */, declaredNames, timeoutSeconds);
                    Map<String, Object> agentCtx = new LinkedHashMap<>();
                    agentCtx.put("execution_token", token);
                    input.put("__agentspan_ctx__", agentCtx);
                }
            } catch (Exception e) {
                log.warn("Failed to mint execution token: {}", e.getMessage());
            }
        }

        startReq.setInput(input);

        Set<String> startWorkerNames = collectSimpleTaskNames(def);
        collectDynamicTransferNames(config, startWorkerNames);
        List<String> requiredWorkers = new ArrayList<>(startWorkerNames);

        // Idempotency: use the key as correlationId and check for existing executions
        if (request.getIdempotencyKey() != null && !request.getIdempotencyKey().isEmpty()) {
            startReq.setCorrelationId(request.getIdempotencyKey());
            String existing = findExistingExecution(def.getName(), request.getIdempotencyKey());
            if (existing != null) {
                log.info(
                        "Idempotent hit: returning existing workflow {} for key '{}'",
                        existing,
                        request.getIdempotencyKey());
                return StartResponse.builder()
                        .executionId(existing)
                        .agentName(def.getName())
                        .requiredWorkers(requiredWorkers)
                        .build();
            }
        }

        String executionId = workflowExecutor.startWorkflow(new StartWorkflowInput(startReq));
        log.info("Started workflow: {} (id={})", def.getName(), executionId);

        // Validate provider AFTER start — workflow is captured for replay
        Optional<String> validationError = validateModelProvider(config);
        if (validationError.isPresent()) {
            log.warn("Provider not configured for agent '{}': {}", config.getName(), validationError.get());
            workflowService.terminateWorkflow(executionId, validationError.get());
        }

        return StartResponse.builder()
                .executionId(executionId)
                .agentName(def.getName())
                .requiredWorkers(requiredWorkers)
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
    public Map<String, Object> searchAgentExecutions(
            int start, int size, String sort, String freeText, String status, String agentName, String sessionId) {
        // Determine which workflow types to query
        List<String> workflowNames;
        if (agentName != null && !agentName.isEmpty()) {
            workflowNames = List.of(agentName);
        } else {
            workflowNames = listAgents().stream().map(AgentSummary::getName).collect(Collectors.toList());
        }

        if (workflowNames.isEmpty()) {
            Map<String, Object> empty = new LinkedHashMap<>();
            empty.put("totalHits", 0L);
            empty.put("results", List.of());
            return empty;
        }

        // Build query string
        String nameList = workflowNames.stream().map(n -> "'" + n + "'").collect(Collectors.joining(","));
        StringBuilder query =
                new StringBuilder("workflowType IN (").append(nameList).append(")");
        if (status != null && !status.isEmpty()) {
            query.append(" AND status = '").append(status).append("'");
        }

        // Use sessionId as freeText search if provided
        String searchText = freeText != null ? freeText : "*";
        if (sessionId != null && !sessionId.isEmpty()) {
            searchText = sessionId;
        }

        SearchResult<WorkflowSummary> searchResult =
                workflowService.searchWorkflows(start, size, sort, searchText, query.toString());

        List<AgentExecutionSummary> results = searchResult.getResults().stream()
                .map(ws -> AgentExecutionSummary.builder()
                        .executionId(ws.getWorkflowId())
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
                .executionId(executionId)
                .agentName(workflow.getWorkflowName())
                .version(workflow.getWorkflowVersion())
                .status(workflow.getStatus().name())
                .input(workflow.getInput())
                .output(workflow.getOutput())
                .currentTask(currentTask)
                .build();
    }

    /** Pause a running agent execution. */
    public void pauseAgent(String executionId) {
        workflowService.pauseWorkflow(executionId);
    }

    /** Resume a paused agent execution. */
    public void resumeAgent(String executionId) {
        workflowService.resumeWorkflow(executionId);
    }

    /** Cancel a running agent execution. */
    public void cancelAgent(String executionId, String reason) {
        workflowService.terminateWorkflow(executionId, reason != null ? reason : "Cancelled by user");
    }

    /**
     * Get an agent execution with its full task list and token usage.
     *
     * <p>Exposed via {@code GET /api/agent/{id}}.  Returns execution metadata,
     * all tasks (for SDK recursive token collection via {@code subWorkflowId}),
     * and pre-computed token usage for LLM tasks in this execution only.</p>
     */
    public AgentRun getExecution(String executionId) {
        Workflow workflow = executionService.getExecutionStatus(executionId, true);

        int promptTokens = 0, completionTokens = 0, totalTokens = 0;
        boolean hasTokens = false;

        List<AgentRun.TaskDetail> tasks = new ArrayList<>();
        for (Task task : workflow.getTasks()) {
            AgentRun.TaskDetail.TaskDetailBuilder tb = AgentRun.TaskDetail.builder()
                    .taskType(task.getTaskType())
                    .referenceTaskName(task.getReferenceTaskName())
                    .status(task.getStatus().name())
                    .subWorkflowId(task.getSubWorkflowId())
                    .outputData(task.getOutputData());
            tasks.add(tb.build());

            if ("LLM_CHAT_COMPLETE".equalsIgnoreCase(task.getTaskType())) {
                Map<String, Object> out = task.getOutputData();
                if (out != null) {
                    promptTokens += toInt(out.get("promptTokens"));
                    completionTokens += toInt(out.get("completionTokens"));
                    totalTokens += toInt(out.get("tokenUsed"));
                    hasTokens = true;
                }
            }
        }

        AgentRun.TokenUsage tokenUsage = hasTokens
                ? AgentRun.TokenUsage.builder()
                        .promptTokens(promptTokens)
                        .completionTokens(completionTokens)
                        .totalTokens(totalTokens == 0 ? promptTokens + completionTokens : totalTokens)
                        .build()
                : null;

        return AgentRun.builder()
                .executionId(executionId)
                .agentName(workflow.getWorkflowName())
                .version(workflow.getWorkflowVersion())
                .status(workflow.getStatus().name())
                .startTime(workflow.getStartTime())
                .endTime(workflow.getEndTime())
                .input(workflow.getInput())
                .output(workflow.getOutput())
                .tokenUsage(tokenUsage)
                .tasks(tasks)
                .build();
    }

    /**
     * Write the agent definition into workflow metadata so it can be inspected
     * later without re-running the agent.  Stores the raw serialized config
     * sent by the SDK — tools and guardrails are already reduced to name
     * references by the SDK serializer, so no function objects are present.
     */
    private void stampAgentDef(Map<String, Object> metadata, StartRequest request) {
        Map<String, Object> agentDef = request.getRawConfig() != null
                ? request.getRawConfig()
                : (request.getAgentConfig() != null ? MAPPER.convertValue(request.getAgentConfig(), Map.class) : null);
        if (agentDef != null) {
            metadata.put("agentDef", agentDef);
        }
    }

    private static int toInt(Object value) {
        if (value instanceof Number) return ((Number) value).intValue();
        if (value instanceof String) {
            try {
                return Integer.parseInt((String) value);
            } catch (NumberFormatException ignored) {
            }
        }
        return 0;
    }

    private void validateStartInput(StartRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("Start request is required");
        }
        if (hasMeaningfulText(request.getPrompt())
                || hasMeaningfulMedia(request.getMedia())
                || hasMeaningfulContext(request.getContext())) {
            return;
        }
        throw new IllegalArgumentException(
                "Agent execution requires a non-empty prompt, at least one media item, or non-empty context.");
    }

    private boolean hasMeaningfulText(String text) {
        return text != null && !text.isBlank();
    }

    private boolean hasMeaningfulMedia(List<String> media) {
        if (media == null || media.isEmpty()) {
            return false;
        }
        return media.stream().anyMatch(item -> item != null && !item.isBlank());
    }

    private boolean hasMeaningfulContext(Map<String, Object> context) {
        return context != null && !context.isEmpty();
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getAgentDef(String name, Integer version) {
        WorkflowDef def;
        if (version != null) {
            def = metadataDAO
                    .getWorkflowDef(name, version)
                    .orElseThrow(() -> new IllegalArgumentException("Agent not found: " + name + " v" + version));
        } else {
            def = metadataDAO
                    .getLatestWorkflowDef(name)
                    .orElseThrow(() -> new IllegalArgumentException("Agent not found: " + name));
        }
        Map<String, Object> metadata = def.getMetadata();
        if (metadata != null && metadata.get("agentDef") instanceof Map) {
            return (Map<String, Object>) metadata.get("agentDef");
        }
        throw new IllegalArgumentException("No agent definition found for: " + name);
    }

    public void deleteAgent(String name, Integer version) {
        if (version != null) {
            metadataDAO.removeWorkflowDef(name, version);
        } else {
            // Remove latest version
            WorkflowDef def = metadataDAO
                    .getLatestWorkflowDef(name)
                    .orElseThrow(() -> new IllegalArgumentException("Agent not found: " + name));
            metadataDAO.removeWorkflowDef(name, def.getVersion());
        }
    }

    /**
     * Search for an existing workflow with the given correlationId (idempotency key).
     * Returns the execution ID if a RUNNING or COMPLETED execution exists, null otherwise.
     */
    private String findExistingExecution(String workflowName, String idempotencyKey) {
        try {
            String query = "workflowType = '" + workflowName + "' AND status IN ('RUNNING', 'COMPLETED')";
            SearchResult<WorkflowSummary> results =
                    workflowService.searchWorkflows(0, 1, "startTime:DESC", idempotencyKey, query);
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
     * Extract credential names declared in tool configs (for execution token bounding).
     */
    private List<String> extractDeclaredCredentials(AgentConfig config) {
        Set<String> names = new LinkedHashSet<>();
        collectCredentialsRecursive(config, names);
        return new ArrayList<>(names);
    }

    private void collectCredentialsRecursive(AgentConfig config, Set<String> names) {
        // Agent-level credentials
        if (config.getCredentials() != null) {
            names.addAll(config.getCredentials());
        }
        // Tool-level credentials
        if (config.getTools() != null) {
            for (ToolConfig tool : config.getTools()) {
                if (tool.getConfig() != null && tool.getConfig().get("credentials") instanceof List<?> creds) {
                    for (Object c : creds) {
                        if (c instanceof String s) names.add(s);
                    }
                }
                // Recurse into agent_tool nested agents
                if ("agent_tool".equals(tool.getToolType()) && tool.getConfig() != null) {
                    Object nested = tool.getConfig().get("agentConfig");
                    if (nested instanceof Map<?, ?> nestedMap) {
                        try {
                            AgentConfig nestedConfig = new ObjectMapper().convertValue(nestedMap, AgentConfig.class);
                            collectCredentialsRecursive(nestedConfig, names);
                        } catch (Exception e) {
                            // Skip if can't parse nested config
                        }
                    }
                }
            }
        }
        // Recurse into sub-agents (multi-agent strategies)
        if (config.getAgents() != null) {
            for (AgentConfig sub : config.getAgents()) {
                collectCredentialsRecursive(sub, names);
            }
        }
    }

    /**
     * Walk the agent tree and register task definitions for all worker tools.
     */
    private void registerTaskDefinitions(AgentConfig config) {
        Set<String> registered = new HashSet<>();
        collectAndRegisterTasks(config, registered);
    }

    @SuppressWarnings("unchecked")
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

        // Register termination worker (compiled as SIMPLE task by TerminationCompiler)
        if (config.getTermination() != null) {
            String taskName = config.getName() + "_termination";
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

        // Register callable gate workers (text_contains gates are INLINE, no registration needed)
        if (config.getGate() != null && config.getGate().get("taskName") instanceof String gateTaskName) {
            if (!registered.contains(gateTaskName)) {
                registerTaskDef(gateTaskName);
                registered.add(gateTaskName);
            }
        }

        // Register callable instructions worker (_worker_ref in instructions map)
        if (config.getInstructions() instanceof Map<?, ?> instrMap
                && instrMap.get("_worker_ref") instanceof String instrTaskName
                && !instrTaskName.isBlank()) {
            if (!registered.contains(instrTaskName)) {
                registerTaskDef(instrTaskName);
                registered.add(instrTaskName);
            }
        }

        // Register worker-based router (WorkerRef with taskName)
        if (config.getRouter() instanceof Map<?, ?> routerMap
                && routerMap.get("taskName") instanceof String routerTaskName) {
            if (!registered.contains(routerTaskName)) {
                registerTaskDef(routerTaskName);
                registered.add(routerTaskName);
            }
        } else if (config.getRouter() instanceof WorkerRef workerRef && workerRef.getTaskName() != null) {
            if (!registered.contains(workerRef.getTaskName())) {
                registerTaskDef(workerRef.getTaskName());
                registered.add(workerRef.getTaskName());
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

        // Register check_transfer worker for hybrid (has both agents AND tools)
        if (config.getAgents() != null
                && !config.getAgents().isEmpty()
                && config.getTools() != null
                && !config.getTools().isEmpty()) {
            String taskName = config.getName() + "_check_transfer";
            if (!registered.contains(taskName)) {
                registerTaskDef(taskName);
                registered.add(taskName);
            }
        }

        // Register check_transfer workers for swarm sub-agents
        // In swarm mode, each sub-agent gets a {name}_check_transfer SIMPLE task
        if ("swarm".equals(config.getStrategy()) && config.getAgents() != null) {
            for (AgentConfig sub : config.getAgents()) {
                String taskName = sub.getName() + "_check_transfer";
                if (!registered.contains(taskName)) {
                    registerTaskDef(taskName);
                    registered.add(taskName);
                }
            }
        }

        // Register transfer_to_ workers for swarm agents
        // Each agent gets {source}_transfer_to_{peer} — matching MultiAgentCompiler
        if ("swarm".equals(config.getStrategy()) && config.getAgents() != null) {
            List<String> allNames = new ArrayList<>();
            allNames.add(config.getName());
            for (AgentConfig sub : config.getAgents()) {
                allNames.add(sub.getName());
            }
            for (String source : allNames) {
                for (String peer : allNames) {
                    if (!source.equals(peer)) {
                        String taskName = source + "_transfer_to_" + peer;
                        if (!registered.contains(taskName)) {
                            registerTaskDef(taskName);
                            registered.add(taskName);
                        }
                    }
                }
            }
        }

        // Register transfer_to_ workers for hybrid agents (has both tools and sub-agents)
        if (config.getAgents() != null
                && !config.getAgents().isEmpty()
                && config.getTools() != null
                && !config.getTools().isEmpty()) {
            for (AgentConfig sub : config.getAgents()) {
                String taskName = config.getName() + "_transfer_to_" + sub.getName();
                if (!registered.contains(taskName)) {
                    registerTaskDef(taskName);
                    registered.add(taskName);
                }
            }
        }

        // Register graph-structure node workers and router workers
        if (config.getMetadata() != null && config.getMetadata().get("_graph_structure") instanceof Map<?, ?> graph) {
            // Node workers
            if (graph.get("nodes") instanceof List<?> nodes) {
                for (Object nodeObj : nodes) {
                    if (nodeObj instanceof Map<?, ?> node && node.get("_worker_ref") instanceof String workerRef) {
                        if (!registered.contains(workerRef)) {
                            registerTaskDef(workerRef);
                            registered.add(workerRef);
                        }
                    }
                }
            }
            // Conditional edge router workers
            if (graph.get("conditional_edges") instanceof List<?> condEdges) {
                for (Object ceObj : condEdges) {
                    if (ceObj instanceof Map<?, ?> ce && ce.get("_router_ref") instanceof String routerRef) {
                        if (!registered.contains(routerRef)) {
                            registerTaskDef(routerRef);
                            registered.add(routerRef);
                        }
                    }
                }
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
                    log.warn(
                            "Unexpected agentConfig type for tool '{}': {}", tool.getName(), agentConfigObj.getClass());
                    continue;
                }

                // Recursively register any nested agent_tool workflows
                registerAgentToolWorkflows(childConfig);

                // Compile and register the child agent workflow
                WorkflowDef childDef = agentCompiler.compile(childConfig);
                metadataDAO.updateWorkflowDef(childDef);
                log.info("Registered agent_tool child workflow: {} for tool '{}'", childDef.getName(), tool.getName());

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
            // Skip validation for Claude Code agents — they use a passthrough
            // worker, not a server-side LLM provider.
            if (!config.getModel().startsWith("claude-code")) {
                ModelParser.ParsedModel parsed = ModelParser.parse(config.getModel());
                Optional<String> error = providerValidator.validateProvider(parsed.getProvider());
                if (error.isPresent()) return error;
            }
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
     * Open an SSE stream for an agent execution. Replays missed events on reconnect.
     */
    public SseEmitter openStream(String executionId, Long lastEventId) {
        log.info("Opening SSE stream for execution {} (lastEventId={})", executionId, lastEventId);
        return streamRegistry.register(executionId, lastEventId);
    }

    /**
     * Respond to a pending HITL task in an agent execution.
     */
    public void respond(String executionId, Map<String, Object> output) {
        log.info("Responding to execution {}: {}", executionId, output);

        // Find the pending task (HUMAN type, IN_PROGRESS status)
        Workflow workflow = executionService.getExecutionStatus(executionId, true);
        Task pendingTask = null;
        for (Task task : workflow.getTasks()) {
            if ("HUMAN".equals(task.getTaskType()) && task.getStatus() == Task.Status.IN_PROGRESS) {
                pendingTask = task;
                break;
            }
        }

        if (pendingTask == null) {
            throw new IllegalStateException("No pending HUMAN task found in execution " + executionId);
        }

        // Update the task with the human's response
        TaskResult taskResult = new TaskResult();
        taskResult.setTaskId(pendingTask.getTaskId());
        taskResult.setWorkflowInstanceId(executionId);
        taskResult.setStatus(TaskResult.Status.COMPLETED);
        Map<String, Object> outputData =
                new LinkedHashMap<>(pendingTask.getOutputData() != null ? pendingTask.getOutputData() : Map.of());
        outputData.putAll(output);
        taskResult.setOutputData(outputData);
        executionService.updateTask(taskResult);
        log.info("Completed HUMAN task {} in execution {}", pendingTask.getReferenceTaskName(), executionId);
    }

    /**
     * Get the current status of an agent execution.
     */
    public Map<String, Object> getStatus(String executionId) {
        Workflow workflow = executionService.getExecutionStatus(executionId, true);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("executionId", executionId);
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
            if ("HUMAN".equals(task.getTaskType()) && task.getStatus() == Task.Status.IN_PROGRESS) {
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

    // ── Framework event push ─────────────────────────────────────────

    /**
     * Translate a framework event map (from Python worker HTTP push) to an
     * AgentSSEEvent and fan it out to all registered SSE emitters.
     * Silently ignored if no clients are connected.
     */
    public void pushFrameworkEvent(String executionId, Map<String, Object> event) {
        String type = event.getOrDefault("type", "").toString();
        AgentSSEEvent sseEvent =
                switch (type) {
                    case "thinking" -> AgentSSEEvent.thinking(
                            executionId, event.getOrDefault("content", "").toString());
                    case "tool_call" -> AgentSSEEvent.toolCall(
                            executionId, event.getOrDefault("toolName", "").toString(), event.get("args"));
                    case "tool_result" -> AgentSSEEvent.toolResult(
                            executionId,
                            event.getOrDefault("toolName", "").toString(),
                            event.getOrDefault("result", ""));
                    case "context_condensed" -> AgentSSEEvent.contextCondensed(
                            executionId,
                            event.getOrDefault("trigger", "").toString(),
                            event.get("messagesBefore") instanceof Number n ? n.intValue() : 0,
                            event.get("messagesAfter") instanceof Number n ? n.intValue() : 0,
                            event.get("exchangesCondensed") instanceof Number n ? n.intValue() : 0);
                    case "subagent_start" -> AgentSSEEvent.subagentStart(
                            executionId,
                            extractSubagentIdentifier(event),
                            event.getOrDefault("prompt", "").toString());
                    case "subagent_stop" -> AgentSSEEvent.subagentStop(
                            executionId,
                            extractSubagentIdentifier(event),
                            event.getOrDefault("result", "").toString());
                    default -> {
                        log.debug("Unknown framework event type '{}' for execution {}", type, executionId);
                        yield null;
                    }
                };
        if (sseEvent != null) {
            streamRegistry.send(executionId, sseEvent);
        }
    }

    private String extractSubagentIdentifier(Map<String, Object> event) {
        // Tier 2/3: subWorkflowId is set; Tier 1 native subagents: agentId is set
        Object subWorkflowId = event.get("subWorkflowId");
        if (subWorkflowId != null && !subWorkflowId.toString().isBlank()) {
            return subWorkflowId.toString();
        }
        Object agentId = event.get("agentId");
        return agentId != null ? agentId.toString() : "unknown";
    }

    // ── Task registration ────────────────────────────────────────────

    private void registerTaskDef(String taskName) {
        TaskDef taskDef = new TaskDef();
        taskDef.setName(taskName);
        taskDef.setRetryCount(2);
        taskDef.setRetryDelaySeconds(2);
        taskDef.setRetryLogic(TaskDef.RetryLogic.LINEAR_BACKOFF);
        taskDef.setTimeoutSeconds(0);
        taskDef.setResponseTimeoutSeconds(3600);
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

    // ── Utility: collect SIMPLE task names from workflow tree ────────

    /**
     * Walk a compiled WorkflowDef tree and return the names of every SIMPLE task.
     * SDKs use this list to know exactly which workers to register.
     */
    private Set<String> collectSimpleTaskNames(WorkflowDef workflowDef) {
        Set<String> names = new LinkedHashSet<>();
        collectSimpleTaskNamesFromTasks(workflowDef.getTasks(), names);
        return names;
    }

    /**
     * Collect dynamically-dispatched swarm/hybrid transfer tool task names from the agent config.
     * These tasks are created at runtime by FORK (based on LLM tool calls) and are not
     * statically present in the compiled WorkflowDef, so collectSimpleTaskNames misses them.
     */
    private void collectDynamicTransferNames(AgentConfig config, Set<String> names) {
        if (config == null) return;
        // Swarm: {source}_transfer_to_{peer} for each pair
        if ("swarm".equals(config.getStrategy()) && config.getAgents() != null && !config.getAgents().isEmpty()) {
            List<String> allNames = new ArrayList<>();
            allNames.add(config.getName());
            for (AgentConfig sub : config.getAgents()) {
                allNames.add(sub.getName());
            }
            for (String src : allNames) {
                for (String dst : allNames) {
                    if (!src.equals(dst)) {
                        names.add(src + "_transfer_to_" + dst);
                    }
                }
            }
        }
        // Hybrid: {parent}_transfer_to_{sub} for agents with both tools and sub-agents
        if (config.getAgents() != null && !config.getAgents().isEmpty()
                && config.getTools() != null && !config.getTools().isEmpty()) {
            for (AgentConfig sub : config.getAgents()) {
                names.add(config.getName() + "_transfer_to_" + sub.getName());
            }
        }
        // Recurse into sub-agents
        if (config.getAgents() != null) {
            for (AgentConfig sub : config.getAgents()) {
                collectDynamicTransferNames(sub, names);
            }
        }
    }

    private void collectSimpleTaskNamesFromTasks(List<WorkflowTask> tasks, Set<String> names) {
        if (tasks == null) return;
        for (WorkflowTask task : tasks) {
            if ("SIMPLE".equals(task.getType())) {
                names.add(task.getName());
            }
            // DO_WHILE loop body
            if (task.getLoopOver() != null) {
                collectSimpleTaskNamesFromTasks(task.getLoopOver(), names);
            }
            // SWITCH / DECISION default case
            if (task.getDefaultCase() != null) {
                collectSimpleTaskNamesFromTasks(task.getDefaultCase(), names);
            }
            // SWITCH / DECISION named cases
            if (task.getDecisionCases() != null) {
                for (List<WorkflowTask> caseTasks : task.getDecisionCases().values()) {
                    collectSimpleTaskNamesFromTasks(caseTasks, names);
                }
            }
            // FORK branches
            if (task.getForkTasks() != null) {
                for (List<WorkflowTask> branch : task.getForkTasks()) {
                    collectSimpleTaskNamesFromTasks(branch, names);
                }
            }
            // Inline sub-workflows
            if (task.getSubWorkflowParam() != null && task.getSubWorkflowParam().getWorkflowDef() != null) {
                collectSimpleTaskNamesFromTasks(
                        task.getSubWorkflowParam().getWorkflowDef().getTasks(), names);
            }
        }
    }

    // ── Execution lifecycle (UI delegation) ─────────────────────────

    public Workflow getFullExecution(String executionId) {
        return executionService.getExecutionStatus(executionId, true);
    }

    public void restartExecution(String executionId, boolean useLatestDefinitions) {
        workflowService.restartWorkflow(executionId, useLatestDefinitions);
    }

    public void retryExecution(String executionId, boolean resumeSubworkflowTasks) {
        workflowService.retryWorkflow(executionId, resumeSubworkflowTasks);
    }

    public String rerunExecution(String executionId, RerunWorkflowRequest request) {
        return workflowService.rerunWorkflow(executionId, request);
    }

    public List<Task> getExecutionTasks(String executionId, String status, int count, int start) {
        Workflow wf = executionService.getExecutionStatus(executionId, true);
        List<Task> tasks = wf.getTasks();
        if (status != null && !status.isEmpty()) {
            tasks = tasks.stream()
                    .filter(t -> status.equals(t.getStatus().name()))
                    .collect(Collectors.toList());
        }
        int end = Math.min(start + count, tasks.size());
        if (start >= tasks.size()) return List.of();
        return tasks.subList(start, end);
    }

    public SearchResult<WorkflowSummary> searchExecutionsRaw(
            int start, int size, String sort, String freeText, String query) {
        return workflowService.searchWorkflows(start, size, sort, freeText, query);
    }

    public WorkflowDef getAgentDefinition(String name, Integer version) {
        if (version != null) {
            return metadataDAO
                    .getWorkflowDef(name, version)
                    .orElseThrow(() -> new com.netflix.conductor.core.exception.NotFoundException(
                            "Definition not found: " + name));
        }
        return metadataDAO
                .getLatestWorkflowDef(name)
                .orElseThrow(() ->
                        new com.netflix.conductor.core.exception.NotFoundException("Definition not found: " + name));
    }

    public void updateTaskResult(TaskResult taskResult) {
        executionService.updateTask(taskResult);
    }

    public List<TaskExecLog> getTaskLogs(String taskId) {
        return executionService.getTaskLogs(taskId);
    }
}
