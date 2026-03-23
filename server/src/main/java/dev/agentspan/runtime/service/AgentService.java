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

import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.auth.User;
import dev.agentspan.runtime.compiler.AgentCompiler;
import dev.agentspan.runtime.credentials.ExecutionTokenService;
import dev.agentspan.runtime.model.*;
import dev.agentspan.runtime.normalizer.NormalizerRegistry;
import dev.agentspan.runtime.util.ModelParser;
import dev.agentspan.runtime.util.ProviderValidator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.*;

import lombok.RequiredArgsConstructor;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import java.util.Optional;
import java.util.stream.Collectors;

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
    AgentService(AgentCompiler agentCompiler, NormalizerRegistry normalizerRegistry,
                 MetadataDAO metadataDAO, WorkflowExecutor workflowExecutor,
                 WorkflowService workflowService, AgentStreamRegistry streamRegistry,
                 ExecutionService executionService, ProviderValidator providerValidator,
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
        Map<String, Object> metadata = def.getMetadata() != null
                ? new LinkedHashMap<>(def.getMetadata()) : new LinkedHashMap<>();
        metadata.put("agent_sdk", sdk);
        stampAgentDef(metadata, request);
        def.setMetadata(metadata);

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
        stampAgentDef(metadata, request);
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
        input.put("session_id", request.getSessionId() != null ? request.getSessionId() : "");
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
                User currentUser = RequestContextHolder.get()
                    .map(ctx -> ctx.getUser())
                    .orElse(null);
                if (currentUser != null) {
                    String token = executionTokenService.mint(
                        currentUser.getId(), null /* workflowId not known yet */, declaredNames, timeoutSeconds);
                    Map<String, Object> agentCtx = new LinkedHashMap<>();
                    agentCtx.put("execution_token", token);
                    input.put("__agentspan_ctx__", agentCtx);
                }
            } catch (Exception e) {
                log.warn("Failed to mint execution token: {}", e.getMessage());
            }
        }

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

    /**
     * Get a workflow execution with its full task list and token usage.
     *
     * <p>Exposed via {@code GET /api/agent/{id}}.  Returns workflow metadata,
     * all tasks (for SDK recursive token collection via {@code subWorkflowId}),
     * and pre-computed token usage for LLM tasks in this workflow only.</p>
     */
    public AgentRun getWorkflow(String workflowId) {
        Workflow workflow = executionService.getExecutionStatus(workflowId, true);

        int promptTokens = 0, completionTokens = 0, totalTokens = 0;
        boolean hasTokens = false;

        List<AgentRun.TaskDetail> tasks = new java.util.ArrayList<>();
        for (Task task : workflow.getTasks()) {
            AgentRun.TaskDetail.TaskDetailBuilder tb = AgentRun.TaskDetail.builder()
                    .taskType(task.getTaskType())
                    .referenceTaskName(task.getReferenceTaskName())
                    .status(task.getStatus().name())
                    .subWorkflowId(task.getSubWorkflowId())
                    .outputData(task.getOutputData());
            tasks.add(tb.build());

            if ("LLM_CHAT_COMPLETE".equalsIgnoreCase(task.getTaskType())) {
                java.util.Map<String, Object> out = task.getOutputData();
                if (out != null) {
                    promptTokens     += toInt(out.get("promptTokens"));
                    completionTokens += toInt(out.get("completionTokens"));
                    totalTokens      += toInt(out.get("tokenUsed"));
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
                .workflowId(workflowId)
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
                : (request.getAgentConfig() != null
                        ? MAPPER.convertValue(request.getAgentConfig(), Map.class)
                        : null);
        if (agentDef != null) {
            metadata.put("agentDef", agentDef);
        }
    }

    private static int toInt(Object value) {
        if (value instanceof Number) return ((Number) value).intValue();
        if (value instanceof String) {
            try { return Integer.parseInt((String) value); } catch (NumberFormatException ignored) {}
        }
        return 0;
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
                            AgentConfig nestedConfig = new com.fasterxml.jackson.databind.ObjectMapper()
                                .convertValue(nestedMap, AgentConfig.class);
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

    // ── Framework event push ─────────────────────────────────────────

    /**
     * Translate a framework event map (from Python worker HTTP push) to an
     * AgentSSEEvent and fan it out to all registered SSE emitters.
     * Silently ignored if no clients are connected.
     */
    public void pushFrameworkEvent(String workflowId, Map<String, Object> event) {
        String type = event.getOrDefault("type", "").toString();
        AgentSSEEvent sseEvent = switch (type) {
            case "thinking" -> AgentSSEEvent.thinking(workflowId,
                event.getOrDefault("content", "").toString());
            case "tool_call" -> AgentSSEEvent.toolCall(workflowId,
                event.getOrDefault("toolName", "").toString(),
                event.get("args"));
            case "tool_result" -> AgentSSEEvent.toolResult(workflowId,
                event.getOrDefault("toolName", "").toString(),
                event.getOrDefault("result", ""));
            case "context_condensed" -> AgentSSEEvent.contextCondensed(workflowId,
                event.getOrDefault("trigger", "").toString(),
                event.get("messagesBefore") instanceof Number n ? n.intValue() : 0,
                event.get("messagesAfter") instanceof Number n ? n.intValue() : 0,
                event.get("exchangesCondensed") instanceof Number n ? n.intValue() : 0);
            case "subagent_start" -> AgentSSEEvent.subagentStart(
                workflowId,
                extractSubagentIdentifier(event),
                event.getOrDefault("prompt", "").toString());
            case "subagent_stop" -> AgentSSEEvent.subagentStop(
                workflowId,
                extractSubagentIdentifier(event),
                event.getOrDefault("result", "").toString());
            default -> {
                log.debug("Unknown framework event type '{}' for workflow {}", type, workflowId);
                yield null;
            }
        };
        if (sseEvent != null) {
            streamRegistry.send(workflowId, sseEvent);
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
