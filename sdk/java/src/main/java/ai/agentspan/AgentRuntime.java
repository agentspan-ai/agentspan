// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan;

import ai.agentspan.internal.AgentConfigSerializer;
import ai.agentspan.internal.HttpApi;
import ai.agentspan.internal.SseClient;
import ai.agentspan.internal.WorkerManager;
import ai.agentspan.model.AgentHandle;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.AgentStream;
import ai.agentspan.model.ToolDef;
import ai.agentspan.termination.AndTermination;
import ai.agentspan.termination.MaxMessageTermination;
import ai.agentspan.termination.OrTermination;
import ai.agentspan.termination.TerminationCondition;
import ai.agentspan.termination.TextMentionTermination;
import ai.agentspan.termination.TokenUsageTermination;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

/**
 * Main runtime for executing agents.
 *
 * <p>Manages worker threads, HTTP communication, and agent lifecycle.
 * Implements {@link AutoCloseable} for use in try-with-resources.
 *
 * <p>Example:
 * <pre>{@code
 * try (AgentRuntime runtime = new AgentRuntime()) {
 *     AgentResult result = runtime.run(agent, "Hello!");
 *     result.printResult();
 * }
 * }</pre>
 */
public class AgentRuntime implements AutoCloseable {
    private static final Logger logger = LoggerFactory.getLogger(AgentRuntime.class);

    private final AgentConfig config;
    private final HttpApi httpApi;
    private final WorkerManager workerManager;
    private final AgentConfigSerializer serializer;

    /**
     * Create a runtime using environment variable configuration.
     */
    public AgentRuntime() {
        this(AgentConfig.fromEnv());
    }

    /**
     * Create a runtime with explicit configuration.
     *
     * @param config the agent configuration
     */
    public AgentRuntime(AgentConfig config) {
        this.config = config;
        this.httpApi = new HttpApi(config);
        this.workerManager = new WorkerManager(config);
        this.serializer = new AgentConfigSerializer();
        logger.info("AgentRuntime initialized: {}", config.getServerUrl());
    }

    // ── Synchronous API ──────────────────────────────────────────────────

    /**
     * Compile an agent into a workflow definition without executing it.
     *
     * <p>Serializes the agent and calls {@code POST /api/agent/compile}.
     * Returns the server response containing {@code workflowDef} and
     * {@code requiredWorkers}.
     *
     * <p>Example:
     * <pre>{@code
     * Map<String, Object> plan = runtime.plan(agent);
     * Map<String, Object> workflowDef = (Map<String, Object>) plan.get("workflowDef");
     * }</pre>
     *
     * @param agent the agent to compile
     * @return plan result with workflowDef and requiredWorkers
     */
    public Map<String, Object> plan(Agent agent) {
        Map<String, Object> agentConfig = serializer.serialize(agent);
        logger.debug("Compiling agent '{}'", agent.getName());
        Map<String, Object> result = httpApi.compileAgent(agentConfig);
        logger.info("Agent '{}' compiled successfully", agent.getName());
        return result;
    }

    /**
     * Execute an agent synchronously and return the result.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return the agent result
     */
    public AgentResult run(Agent agent, String prompt) {
        return runAsync(agent, prompt).join();
    }

    /**
     * Start an agent (fire-and-forget) and return a handle.
     *
     * @param agent  the agent to start
     * @param prompt the user's input message
     * @return a handle for monitoring and interacting with the agent
     */
    public AgentHandle start(Agent agent, String prompt) {
        return startAsync(agent, prompt).join();
    }

    /**
     * Execute an agent and stream events as they occur.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return an AgentStream for consuming events
     */
    public AgentStream stream(Agent agent, String prompt) {
        return streamAsync(agent, prompt).join();
    }

    // ── Async API ────────────────────────────────────────────────────────

    /**
     * Execute an agent asynchronously.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to the agent result
     */
    public CompletableFuture<AgentResult> runAsync(Agent agent, String prompt) {
        prepareWorkers(agent);
        workerManager.startAll();

        return startAsync(agent, prompt).thenCompose(handle ->
            CompletableFuture.supplyAsync(() -> handle.waitForResult())
        );
    }

    /**
     * Start an agent asynchronously and return a handle.
     *
     * @param agent  the agent to start
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to an AgentHandle
     */
    public CompletableFuture<AgentHandle> startAsync(Agent agent, String prompt) {
        prepareWorkers(agent);
        workerManager.startAll();

        return CompletableFuture.supplyAsync(() -> {
            Map<String, Object> agentConfig = serializer.serialize(agent);
            String sessionId = agent.getSessionId();

            logger.debug("Starting agent '{}' with prompt: {}", agent.getName(), prompt);

            Map<String, Object> response = httpApi.startAgent(agentConfig, prompt, sessionId);
            String workflowId = extractWorkflowId(response);

            logger.info("Agent '{}' started with workflow ID: {}", agent.getName(), workflowId);
            return new AgentHandle(workflowId, httpApi);
        });
    }

    /**
     * Execute an agent and stream events asynchronously.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to an AgentStream
     */
    public CompletableFuture<AgentStream> streamAsync(Agent agent, String prompt) {
        prepareWorkers(agent);
        workerManager.startAll();

        return startAsync(agent, prompt).thenApply(handle -> {
            String workflowId = handle.getWorkflowId();
            String sseUrl = config.getServerUrl() + "/api/agent/stream/" + workflowId;

            SseClient sseClient = new SseClient(sseUrl, config, httpApi.getHttpClient());
            sseClient.connect();

            return new AgentStream(workflowId, sseClient, httpApi);
        });
    }

    // ── Deploy / Serve / Resume ───────────────────────────────────────────

    /**
     * Compile and register agents on the server without executing them.
     *
     * <p>This is a CI/CD operation. It pushes the workflow definitions and task
     * definitions to the server. It does NOT register local workers or start any
     * processes. Use {@link #serve} separately for the runtime.
     *
     * @param agents one or more agents to deploy
     * @return list of DeploymentInfo, one per deployed agent
     */
    public List<ai.agentspan.model.DeploymentInfo> deploy(Agent... agents) {
        List<ai.agentspan.model.DeploymentInfo> results = new ArrayList<>();
        for (Agent agent : agents) {
            Map<String, Object> agentConfig = serializer.serialize(agent);
            Map<String, Object> payload = new java.util.LinkedHashMap<>();
            payload.put("agentConfig", agentConfig);
            Map<String, Object> resp = httpApi.deployAgent(payload);
            String registeredName = resp.getOrDefault("agentName", agent.getName()).toString();
            results.add(new ai.agentspan.model.DeploymentInfo(registeredName, agent.getName()));
            logger.info("Deployed agent '{}' as '{}'", agent.getName(), registeredName);
        }
        return results;
    }

    /**
     * Async version of {@link #deploy}.
     *
     * @param agents one or more agents to deploy
     * @return CompletableFuture resolving to list of DeploymentInfo
     */
    public CompletableFuture<List<ai.agentspan.model.DeploymentInfo>> deployAsync(Agent... agents) {
        return CompletableFuture.supplyAsync(() -> deploy(agents));
    }

    /**
     * Register workers and keep them polling until interrupted.
     *
     * <p>This is a runtime operation: it registers the Java tool functions as
     * Conductor workers and starts polling for tasks.
     *
     * @param agents agents whose workers should be served
     */
    public void serve(Agent... agents) {
        for (Agent agent : agents) {
            prepareWorkers(agent);
        }
        workerManager.startAll();
        logger.info("Serving {} agent(s) — waiting for tasks (Ctrl+C to stop)", agents.length);
        Runtime.getRuntime().addShutdownHook(new Thread(workerManager::stop, "agentspan-serve-shutdown"));
        try {
            Thread.currentThread().join();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /**
     * Re-attach to an existing agent execution and re-register workers.
     *
     * <p>Fetches the workflow from the server and re-registers tool workers.
     * Returns an {@link ai.agentspan.model.AgentHandle} for continued interaction.
     *
     * @param executionId the execution ID from a previous {@link #start} call
     * @param agent       the same Agent definition that was originally executed
     * @return an AgentHandle bound to this runtime
     */
    public ai.agentspan.model.AgentHandle resume(String executionId, Agent agent) {
        prepareWorkers(agent);
        return new ai.agentspan.model.AgentHandle(executionId, httpApi);
    }

    /**
     * Async version of {@link #resume}.
     *
     * @param executionId the execution ID
     * @param agent       the agent definition originally executed
     * @return CompletableFuture resolving to an AgentHandle
     */
    public CompletableFuture<ai.agentspan.model.AgentHandle> resumeAsync(String executionId, Agent agent) {
        return CompletableFuture.supplyAsync(() -> resume(executionId, agent));
    }

    // ── Lifecycle ────────────────────────────────────────────────────────

    /**
     * Shutdown the runtime, stopping all worker threads.
     */
    public void shutdown() {
        logger.info("Shutting down AgentRuntime");
        workerManager.stop();
    }

    @Override
    public void close() {
        shutdown();
    }

    // ── Internal ─────────────────────────────────────────────────────────

    /**
     * Walk the agent tree and register tool workers with the WorkerManager.
     *
     * @param agent the agent (root or sub-agent)
     */
    public void prepareWorkers(Agent agent) {
        // Register tools for this agent
        for (ToolDef tool : agent.getTools()) {
            if (tool.getFunc() != null && "worker".equals(tool.getToolType())) {
                workerManager.register(tool.getName(), tool.getFunc());
            }
            // Recursively prepare workers for agent_tool child agents
            if ("agent_tool".equals(tool.getToolType()) && tool.getAgentRef() != null) {
                prepareWorkers(tool.getAgentRef());
            }
        }

        // Register callback workers (legacy single-function style)
        if (agent.getBeforeModelCallback() != null) {
            final java.util.function.Function<Map<String, Object>, Map<String, Object>> beforeCb = agent.getBeforeModelCallback();
            workerManager.register(agent.getName() + "_before_model", inputData -> {
                Map<String, Object> result = beforeCb.apply(inputData);
                return result != null ? result : java.util.Collections.emptyMap();
            });
        }
        if (agent.getAfterModelCallback() != null) {
            final java.util.function.Function<Map<String, Object>, Map<String, Object>> afterCb = agent.getAfterModelCallback();
            workerManager.register(agent.getName() + "_after_model", inputData -> {
                Map<String, Object> result = afterCb.apply(inputData);
                return result != null ? result : java.util.Collections.emptyMap();
            });
        }

        // Register CallbackHandler list workers — chain all handlers per position
        if (agent.getCallbacks() != null && !agent.getCallbacks().isEmpty()) {
            final List<CallbackHandler> handlers = agent.getCallbacks();
            final String agentName = agent.getName();
            String[][] positionMethods = {
                {"before_agent", "onAgentStart"},
                {"after_agent",  "onAgentEnd"},
                {"before_model", "onModelStart"},
                {"after_model",  "onModelEnd"},
                {"before_tool",  "onToolStart"},
                {"after_tool",   "onToolEnd"},
            };
            for (String[] pm : positionMethods) {
                String position = pm[0];
                String methodName = pm[1];
                // Find handlers that override this method
                List<CallbackHandler> active = new ArrayList<>();
                for (CallbackHandler h : handlers) {
                    try {
                        java.lang.reflect.Method m = h.getClass().getMethod(methodName, Map.class);
                        if (!m.getDeclaringClass().equals(CallbackHandler.class)) {
                            active.add(h);
                        }
                    } catch (NoSuchMethodException ignored) {}
                }
                if (active.isEmpty()) continue;

                // Only register if not already registered via legacy callbacks
                final List<CallbackHandler> activeHandlers = active;
                final String taskName = agentName + "_" + position;
                final String mName = methodName;
                workerManager.register(taskName, inputData -> {
                    for (CallbackHandler handler : activeHandlers) {
                        try {
                            java.lang.reflect.Method m = handler.getClass().getMethod(mName, Map.class);
                            m.setAccessible(true); // allow invocation on package-private inner classes
                            Map<String, Object> result = (Map<String, Object>) m.invoke(handler, inputData);
                            if (result != null && !result.isEmpty()) return result;
                        } catch (Exception e) {
                            logger.warn("CallbackHandler {} failed for {}: {}", mName, taskName, e.getMessage());
                        }
                    }
                    return java.util.Collections.emptyMap();
                });
            }
        }

        // Register combined guardrail worker per agent (matches Python: {agent_name}_output_guardrail)
        List<ai.agentspan.model.GuardrailDef> customGuardrails = agent.getGuardrails().stream()
            .filter(g -> g.getFunc() != null)
            .collect(java.util.stream.Collectors.toList());
        if (!customGuardrails.isEmpty()) {
            String taskName = agent.getName() + "_output_guardrail";
            workerManager.register(taskName, inputData -> {
                Object rawContent = inputData.get("content");
                String content = rawContent != null ? rawContent.toString() : "";
                int iteration = inputData.get("iteration") instanceof Number
                    ? ((Number) inputData.get("iteration")).intValue() : 0;
                for (ai.agentspan.model.GuardrailDef g : customGuardrails) {
                    ai.agentspan.model.GuardrailResult result = g.getFunc().apply(content);
                    if (!result.isPassed()) {
                        String onFail = g.getOnFail().toJsonValue();
                        String fixedOutput = result.getFixedOutput();
                        if ("retry".equals(onFail) && iteration >= g.getMaxRetries()) onFail = "raise";
                        if ("fix".equals(onFail) && fixedOutput == null) onFail = "raise";
                        Map<String, Object> out = new java.util.LinkedHashMap<>();
                        out.put("passed", false);
                        out.put("message", result.getMessage() != null ? result.getMessage() : "");
                        out.put("on_fail", onFail);
                        out.put("fixed_output", fixedOutput);
                        out.put("guardrail_name", g.getName());
                        out.put("should_continue", "retry".equals(onFail));
                        return out;
                    }
                }
                Map<String, Object> out = new java.util.LinkedHashMap<>();
                out.put("passed", true);
                out.put("message", "");
                out.put("on_fail", "pass");
                out.put("fixed_output", null);
                out.put("guardrail_name", "");
                out.put("should_continue", false);
                return out;
            });
        }

        // Register termination condition worker for agents that have one
        if (agent.getTermination() != null) {
            final TerminationCondition termination = agent.getTermination();
            final String taskName = agent.getName() + "_termination";
            workerManager.register(taskName, input -> {
                String result = input.get("result") instanceof String
                    ? (String) input.get("result") : (input.get("result") != null ? input.get("result").toString() : "");
                int iteration = input.get("iteration") instanceof Number
                    ? ((Number) input.get("iteration")).intValue() : 0;
                boolean shouldContinue = evaluateTermination(termination, result, iteration);
                Map<String, Object> out = new java.util.LinkedHashMap<>();
                out.put("should_continue", shouldContinue);
                out.put("reason", shouldContinue ? "" : "Termination condition met");
                return out;
            });
        }

        // Register local code execution worker
        if (agent.isLocalCodeExecution()) {
            String taskName = agent.getName() + "_execute_code";
            workerManager.register(taskName, inputData -> {
                String language = inputData.get("language") instanceof String
                    ? (String) inputData.get("language") : "python";
                String code = inputData.get("code") instanceof String
                    ? (String) inputData.get("code") : "";
                int timeout = agent.getCodeExecutionTimeout() > 0 ? agent.getCodeExecutionTimeout() : 30;
                return executeCode(language, code, timeout);
            });
        }

        // Register SWARM transfer workers
        if (ai.agentspan.enums.Strategy.SWARM.equals(agent.getStrategy())
                && !agent.getAgents().isEmpty()) {
            registerSwarmWorkers(agent);
        }

        // Register MANUAL process_selection worker.
        // The server creates a {name}_process_selection SIMPLE task after each
        // HUMAN pick-agent task. This worker maps the selected agent name to its
        // positional index (used by the SWITCH task to route to the right sub-agent).
        if (ai.agentspan.enums.Strategy.MANUAL.equals(agent.getStrategy())
                && !agent.getAgents().isEmpty()) {
            registerManualWorkers(agent);
        }

        // Recurse into sub-agents
        for (Agent subAgent : agent.getAgents()) {
            prepareWorkers(subAgent);
        }

        // Router agent
        if (agent.getRouter() != null) {
            prepareWorkers(agent.getRouter());
        }
    }

    /**
     * Evaluate a termination condition given the current LLM result and iteration count.
     *
     * @return {@code true} if the agent should continue (condition NOT met),
     *         {@code false} if the agent should stop (condition IS met)
     */
    private boolean evaluateTermination(TerminationCondition condition, String result, int iteration) {
        if (condition instanceof TextMentionTermination) {
            String text = ((TextMentionTermination) condition).getText();
            boolean found = result != null && result.contains(text);
            return !found; // should_continue = false when text found (stop)
        } else if (condition instanceof MaxMessageTermination) {
            int max = ((MaxMessageTermination) condition).getMaxMessages();
            return iteration < max; // should_continue = false when iteration >= max
        } else if (condition instanceof TokenUsageTermination) {
            // Token counts are not easily available from result text; always continue
            return true;
        } else if (condition instanceof AndTermination) {
            AndTermination and = (AndTermination) condition;
            boolean leftContinue = evaluateTermination(and.getLeft(), result, iteration);
            boolean rightContinue = evaluateTermination(and.getRight(), result, iteration);
            // AND: stop only when BOTH conditions say stop
            return leftContinue || rightContinue;
        } else if (condition instanceof OrTermination) {
            OrTermination or = (OrTermination) condition;
            boolean leftContinue = evaluateTermination(or.getLeft(), result, iteration);
            boolean rightContinue = evaluateTermination(or.getRight(), result, iteration);
            // OR: stop when EITHER condition says stop
            return leftContinue && rightContinue;
        }
        return true; // unknown condition type — keep going
    }

    /**
     * Register SWARM transfer, check_transfer, and handoff_check workers for the given agent.
     *
     * <p>The server creates these worker tasks for SWARM agents:
     * <ul>
     *   <li>{@code {source}_transfer_to_{peer}} — LLM-called transfer tool (complete with empty output)</li>
     *   <li>{@code {name}_check_transfer} — detects if LLM tool_calls contain a transfer</li>
     *   <li>{@code {name}_handoff_check} — determines the next active_agent and whether to loop</li>
     * </ul>
     */
    private void registerSwarmWorkers(Agent swarmAgent) {
        // Collect all participant names: the SWARM orchestrator (case "0") + sub-agents (cases "1", "2", ...)
        List<String> allNames = new ArrayList<>();
        allNames.add(swarmAgent.getName());
        for (Agent sub : swarmAgent.getAgents()) {
            allNames.add(sub.getName());
        }

        // Register {source}_transfer_to_{peer} workers — just complete with empty output
        for (String source : allNames) {
            for (String peer : allNames) {
                if (!source.equals(peer)) {
                    final String taskName = source + "_transfer_to_" + peer;
                    workerManager.register(taskName, input -> java.util.Collections.emptyMap());
                }
            }
        }

        // Register {name}_check_transfer workers for each participant.
        // Input: tool_calls (list of LLM tool calls)
        // Output: is_transfer (boolean), transfer_to (target agent name)
        for (String agentName : allNames) {
            final String prefix = agentName + "_transfer_to_";
            final String taskName = agentName + "_check_transfer";
            workerManager.register(taskName, input -> {
                Object toolCallsRaw = input.get("tool_calls");
                Map<String, Object> out = new java.util.LinkedHashMap<>();
                out.put("is_transfer", false);
                out.put("transfer_to", "");
                if (toolCallsRaw instanceof List) {
                    @SuppressWarnings("unchecked")
                    List<Object> toolCalls = (List<Object>) toolCallsRaw;
                    for (Object tc : toolCalls) {
                        String name = null;
                        if (tc instanceof Map) {
                            @SuppressWarnings("unchecked")
                            Map<String, Object> tcMap = (Map<String, Object>) tc;
                            name = tcMap.get("name") instanceof String ? (String) tcMap.get("name") : null;
                            if (name == null && tcMap.get("function") instanceof Map) {
                                @SuppressWarnings("unchecked")
                                Map<String, Object> fn = (Map<String, Object>) tcMap.get("function");
                                name = fn.get("name") instanceof String ? (String) fn.get("name") : null;
                            }
                        }
                        if (name != null && name.startsWith(prefix)) {
                            String target = name.substring(prefix.length());
                            out.put("is_transfer", true);
                            out.put("transfer_to", target);
                            break;
                        }
                    }
                }
                return out;
            });
        }

        // Register {swarmAgent.name}_handoff_check worker.
        // Determines the next active_agent index (string: "0"=parent, "1"=first sub, etc.)
        // and whether to continue looping (handoff=true).
        // Input: is_transfer (bool), transfer_to (agent name), active_agent (string index)
        final List<String> subNames = new ArrayList<>();
        for (Agent sub : swarmAgent.getAgents()) {
            subNames.add(sub.getName());
        }
        final String handoffTaskName = swarmAgent.getName() + "_handoff_check";
        workerManager.register(handoffTaskName, input -> {
            Object isTransferRaw = input.get("is_transfer");
            boolean isTransfer = Boolean.TRUE.equals(isTransferRaw)
                || "true".equalsIgnoreCase(isTransferRaw != null ? isTransferRaw.toString() : "");
            String transferTo = input.get("transfer_to") instanceof String
                ? (String) input.get("transfer_to") : "";
            String currentAgent = input.get("active_agent") instanceof String
                ? (String) input.get("active_agent") : "0";

            Map<String, Object> out = new java.util.LinkedHashMap<>();
            if (isTransfer && !transferTo.isEmpty()) {
                // Find the case index for the target agent
                int targetIdx = subNames.indexOf(transferTo);
                if (targetIdx >= 0) {
                    // Sub-agents are cases "1".."N"
                    out.put("active_agent", String.valueOf(targetIdx + 1));
                    out.put("handoff", true);
                } else if (transferTo.equals(swarmAgent.getName())) {
                    // Transfer back to parent (case "0")
                    out.put("active_agent", "0");
                    out.put("handoff", true);
                } else {
                    out.put("active_agent", currentAgent);
                    out.put("handoff", false);
                }
            } else {
                out.put("active_agent", currentAgent);
                out.put("handoff", false);
            }
            return out;
        });
    }

    /**
     * Register the {@code {name}_process_selection} worker for MANUAL strategy agents.
     *
     * <p>The server's MANUAL workflow loop has:
     * <ol>
     *   <li>HUMAN task ({@code {name}_pick_agent}) — pauses for human selection</li>
     *   <li>SIMPLE task ({@code {name}_process_selection}) — maps agent name → index</li>
     *   <li>SWITCH task routes to the selected sub-agent sub-workflow</li>
     * </ol>
     * This worker receives {@code {"human_output": {"selected": "<agentName>"}}} and
     * returns {@code {"selected": "<index>"}} where the index is the 0-based position
     * of the selected agent in the agents list.
     */
    @SuppressWarnings("unchecked")
    private void registerManualWorkers(Agent manualAgent) {
        List<Agent> subAgents = manualAgent.getAgents();
        Map<String, String> nameToIndex = new java.util.HashMap<>();
        for (int i = 0; i < subAgents.size(); i++) {
            nameToIndex.put(subAgents.get(i).getName(), String.valueOf(i));
        }

        final String taskName = manualAgent.getName() + "_process_selection";
        workerManager.register(taskName, inputData -> {
            String selected = null;
            Object humanOutput = inputData.get("human_output");
            if (humanOutput instanceof Map) {
                Object sel = ((Map<Object, Object>) humanOutput).get("selected");
                if (sel instanceof String) {
                    selected = (String) sel;
                }
            }
            String index = (selected != null) ? nameToIndex.get(selected) : null;
            if (index == null) {
                logger.warn("MANUAL process_selection: unknown agent '{}'; defaulting to 0", selected);
                index = "0";
            }
            Map<String, Object> out = new java.util.HashMap<>();
            out.put("selected", index);
            return out;
        });
    }

    private Map<String, Object> executeCode(String language, String code, int timeoutSeconds) {
        Map<String, Object> result = new java.util.LinkedHashMap<>();
        try {
            String interpreter;
            switch (language.toLowerCase()) {
                case "python": case "python3": interpreter = "python3"; break;
                case "bash": case "sh": interpreter = "bash"; break;
                case "node": case "javascript": interpreter = "node"; break;
                default: interpreter = language;
            }
            // Write code to temp file
            java.io.File tmpFile = java.io.File.createTempFile("agentspan_code_",
                language.startsWith("python") ? ".py" : ".sh");
            tmpFile.deleteOnExit();
            try (java.io.FileWriter fw = new java.io.FileWriter(tmpFile)) {
                fw.write(code);
            }

            ProcessBuilder pb = new ProcessBuilder(interpreter, tmpFile.getAbsolutePath());
            pb.redirectErrorStream(true);
            Process process = pb.start();

            boolean finished = process.waitFor(timeoutSeconds, java.util.concurrent.TimeUnit.SECONDS);
            String output = new String(process.getInputStream().readAllBytes());

            if (!finished) {
                process.destroyForcibly();
                result.put("output", output);
                result.put("error", "Code execution timed out after " + timeoutSeconds + "s");
                result.put("exit_code", -1);
                result.put("success", false);
            } else {
                result.put("output", output);
                result.put("exit_code", process.exitValue());
                result.put("success", process.exitValue() == 0);
                if (process.exitValue() != 0) {
                    result.put("error", "Process exited with code " + process.exitValue());
                }
            }
            tmpFile.delete();
        } catch (Exception e) {
            result.put("output", "");
            result.put("error", e.getMessage());
            result.put("exit_code", -1);
            result.put("success", false);
        }
        return result;
    }

    private String extractWorkflowId(Map<String, Object> response) {
        // Try several possible keys — server renamed workflowId → executionId
        Object id = response.get("executionId");
        if (id != null) return id.toString();

        id = response.get("workflowId");
        if (id != null) return id.toString();

        id = response.get("id");
        if (id != null) return id.toString();

        id = response.get("correlationId");
        if (id != null) return id.toString();

        // If only one value in the map, use it
        if (response.size() == 1) {
            return response.values().iterator().next().toString();
        }

        throw new RuntimeException("Cannot extract workflow ID from response: " + response);
    }
}
