// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.internal;

import ai.agentspan.AgentConfig;
import ai.agentspan.Credentials;
import ai.agentspan.exceptions.CredentialAuthException;
import ai.agentspan.exceptions.CredentialNotFoundException;
import ai.agentspan.exceptions.CredentialRateLimitException;
import ai.agentspan.exceptions.CredentialServiceException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.lang.reflect.Method;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;

/**
 * Manages worker threads that poll the server for pending tasks and execute tool functions.
 */
public class WorkerManager {
    private static final Logger logger = LoggerFactory.getLogger(WorkerManager.class);

    /** Minimum Java version required for virtual threads. */
    private static final int VIRTUAL_THREAD_MIN_VERSION = 21;

    private final AgentConfig config;
    private final WorkerHttp workerHttp;
    private final WorkerCredentialFetcher credentialFetcher;
    private final ConcurrentHashMap<String, Function<Map<String, Object>, Object>> handlers;
    /** Optional worker domain per task name. Tasks without an entry poll the default queue. */
    private final ConcurrentHashMap<String, String> taskDomains;
    /** Declared credential names per task name. Empty list when no secrets are declared. */
    private final ConcurrentHashMap<String, List<String>> taskCredentials;
    /**
     * Domain applied by the no-arg {@link #register(String, Function)} overload.
     * AgentRuntime sets this for the lifetime of a single
     * {@code prepareWorkers(agent, domain)} call so all subsequent register
     * calls (callbacks, guardrails, gates, swarm-transfer, etc.) register
     * under the same per-execution domain without having to thread the value
     * through every call site.
     */
    private volatile String currentDomain;
    private ScheduledExecutorService scheduledExecutorService;
    private final ConcurrentHashMap<String, ScheduledFuture<?>> workerFutures;

    private static final int JAVA_VERSION = detectJavaVersion();

    public WorkerManager(AgentConfig config) {
        this.config = config;
        HttpApi httpApi = new HttpApi(config);
        this.workerHttp = new WorkerHttp(httpApi);
        this.credentialFetcher = new WorkerCredentialFetcher(httpApi);
        this.handlers = new ConcurrentHashMap<>();
        this.taskDomains = new ConcurrentHashMap<>();
        this.taskCredentials = new ConcurrentHashMap<>();
        this.workerFutures = new ConcurrentHashMap<>();
    }

    /**
     * Register a task handler function for the given task name.
     *
     * @param taskName the Conductor task type name
     * @param handler  the function to call when a task is polled
     */
    public void register(String taskName, Function<Map<String, Object>, Object> handler) {
        register(taskName, handler, currentDomain);
    }

    /**
     * Set the domain that the no-arg {@link #register(String, Function)}
     * overload will apply to subsequent calls. Pass {@code null} to clear.
     * Used by {@code AgentRuntime.prepareWorkers(agent, domain)} so the many
     * internal worker registrations in that method all pick up the run's
     * domain without per-call wiring.
     */
    public void setCurrentDomain(String domain) {
        this.currentDomain = domain;
    }

    /** Read the domain set by the most recent {@link #setCurrentDomain(String)}. */
    public String getCurrentDomain() {
        return currentDomain;
    }

    /**
     * Register a task handler function scoped to a worker domain.
     *
     * <p>When {@code domain} is non-null, the worker polls
     * {@code /api/tasks/poll/{taskName}?domain={domain}} — only tasks routed
     * to that domain (i.e. tasks belonging to the matching stateful run) are
     * returned. This is the worker-side complement of the {@code runId}
     * passed on {@code /api/agent/start}.
     *
     * @param taskName the Conductor task type name
     * @param handler  the function to call when a task is polled
     * @param domain   optional worker domain (per-stateful-run UUID), or null
     */
    public void register(
            String taskName,
            Function<Map<String, Object>, Object> handler,
            String domain) {
        register(taskName, handler, domain, Collections.emptyList());
    }

    /**
     * Register a task handler scoped to a domain AND declaring a list of
     * credential names that the worker should resolve from the server before
     * invoking the handler. Resolved values are available to the handler via
     * {@link ai.agentspan.Credentials#get(String)}.
     */
    public void register(
            String taskName,
            Function<Map<String, Object>, Object> handler,
            String domain,
            List<String> credentials) {
        boolean reRegister = handlers.containsKey(taskName);
        handlers.put(taskName, handler);
        if (domain != null && !domain.isEmpty()) {
            taskDomains.put(taskName, domain);
        } else {
            taskDomains.remove(taskName);
        }
        if (credentials != null && !credentials.isEmpty()) {
            taskCredentials.put(taskName, List.copyOf(credentials));
        } else {
            taskCredentials.remove(taskName);
        }
        if (reRegister) {
            logger.debug("Re-registering existing handler for task: {} (domain={})", taskName, domain);
            return;
        }
        logger.info("Registered worker for task: {} (domain={})", taskName, domain);

        // Register task definition on the server
        try {
            workerHttp.registerTaskDef(taskName);
        } catch (Exception e) {
            logger.debug("Could not register task def {} (may already exist): {}", taskName, e.getMessage());
        }

        // If the executor is already running, start a polling thread immediately
        // (workers registered after startAll() would otherwise never get polled)
        if (scheduledExecutorService != null && !scheduledExecutorService.isShutdown()) {
            startWorkerForTask(taskName);
        }
    }

    /**
     * Start polling workers for all registered task types.
     */
    public void startAll() {
        if (scheduledExecutorService != null && !scheduledExecutorService.isShutdown()) {
            return; // Already started
        }

        scheduledExecutorService = Executors.newScheduledThreadPool(config.getWorkerThreadCount());

        for (String taskName : handlers.keySet()) {
            startWorkerForTask(taskName);
        }

        logger.info("Started {} worker(s) for {} task(s)",
            config.getWorkerThreadCount(), handlers.size());
    }

    private void startWorkerForTask(String taskName) {
        ScheduledFuture<?> future = scheduledExecutorService.scheduleAtFixedRate(
            () -> pollAndExecute(taskName),
            0,
            config.getWorkerPollIntervalMs(),
            TimeUnit.MILLISECONDS
        );
        workerFutures.put(taskName, future);
    }

    /**
     * Stop all polling workers.
     */
    public void stop() {
        if (scheduledExecutorService != null) {
            scheduledExecutorService.shutdownNow();
            try {
                if (!scheduledExecutorService.awaitTermination(5, TimeUnit.SECONDS)) {
                    logger.warn("Worker manager did not terminate cleanly");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            logger.info("Worker manager stopped");
        }
    }

    private void pollAndExecute(String taskName) {
        Function<Map<String, Object>, Object> handler = handlers.get(taskName);
        if (handler == null) return;

        try {
            String domain = taskDomains.get(taskName);
            Map<String, Object> task = workerHttp.pollTask(taskName, domain);
            if (task == null) return;

            String taskId = (String) task.get("taskId");
            if (taskId == null) {
                taskId = (String) task.get("id");
            }
            if (taskId == null) return;

            String workflowInstanceId = (String) task.get("workflowInstanceId");

            @SuppressWarnings("unchecked")
            Map<String, Object> inputData = (Map<String, Object>) task.getOrDefault("inputData", Map.of());

            logger.debug("Executing task {} ({})", taskName, taskId);

            final String finalTaskId = taskId;
            final String finalWorkflowId = workflowInstanceId;
            executeTask(taskName, finalTaskId, finalWorkflowId, handler, inputData);

        } catch (Exception e) {
            logger.error("Error in poll loop for task {}: {}", taskName, e.getMessage(), e);
        }
    }

    private void executeTask(
            String taskName,
            String taskId,
            String workflowInstanceId,
            Function<Map<String, Object>, Object> handler,
            Map<String, Object> inputData) {

        Runnable task = () -> {
            // Resolve declared secrets BEFORE invoking the handler. Credential
            // failures map to terminal task failures so Conductor doesn't burn
            // retries on a configuration problem. See
            // docs/design/secret-injection-contract.md — Java is tier-1-only
            // (System.getenv is immutable; values reach the handler via the
            // Secrets thread-local accessor, not via env mutation).
            Map<String, String> resolvedSecrets = Collections.emptyMap();
            List<String> declared = taskCredentials.getOrDefault(taskName, Collections.emptyList());
            if (!declared.isEmpty()) {
                String execToken = extractExecutionToken(inputData);
                try {
                    resolvedSecrets = credentialFetcher.fetch(execToken, declared);
                } catch (CredentialNotFoundException | CredentialAuthException
                        | CredentialRateLimitException | CredentialServiceException ce) {
                    logger.error("Credential resolution failed for task {} ({}): {}",
                            taskName, taskId, ce.getMessage());
                    workerHttp.failTaskTerminal(taskId, workflowInstanceId,
                            "Credential resolution failed: " + ce.getMessage());
                    return;
                }
            }

            try {
                Credentials.setForCall(resolvedSecrets);
                try {
                    Object result = handler.apply(inputData);
                    Map<String, Object> output = buildOutput(result);
                    workerHttp.completeTask(taskId, workflowInstanceId, output);
                    logger.debug("Completed task {} ({})", taskName, taskId);
                } finally {
                    Credentials.clearForCall();
                }
            } catch (Exception e) {
                logger.error("Task {} ({}) failed: {}", taskName, taskId, e.getMessage(), e);
                workerHttp.failTask(taskId, workflowInstanceId, e.getMessage());
            }
        };

        if (JAVA_VERSION >= VIRTUAL_THREAD_MIN_VERSION) {
            runInVirtualThread(task);
        } else {
            // Run in the scheduled executor thread pool
            task.run();
        }
    }

    /**
     * Use reflection to create a virtual thread (Java 21+) without requiring compile-time Java 21.
     */
    private void runInVirtualThread(Runnable task) {
        try {
            Class<?> threadClass = Thread.class;
            Method ofVirtualMethod = threadClass.getMethod("ofVirtual");
            Object builderObj = ofVirtualMethod.invoke(null);
            Method startMethod = builderObj.getClass().getMethod("start", Runnable.class);
            startMethod.invoke(builderObj, task);
        } catch (Exception e) {
            // Fallback to regular thread if virtual thread creation fails
            Thread t = new Thread(task, "agentspan-worker");
            t.setDaemon(true);
            t.start();
        }
    }

    /**
     * Pull the execution token out of {@code inputData["__agentspan_ctx__"]["execution_token"]}.
     * Server-side property name is snake-case (matches the .NET / TS extraction).
     * Returns {@code null} if no token is present — caller treats that as
     * "credential resolution will fail with NotFound".
     */
    @SuppressWarnings("unchecked")
    private static String extractExecutionToken(Map<String, Object> inputData) {
        if (inputData == null) return null;
        Object ctx = inputData.get("__agentspan_ctx__");
        if (!(ctx instanceof Map<?, ?> ctxMap)) return null;
        Object token = ctxMap.get("execution_token");
        if (token == null) token = ctxMap.get("executionToken");  // tolerate camelCase
        return token instanceof String s ? s : null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> buildOutput(Object result) {
        if (result == null) return Map.of();
        if (result instanceof Map) return (Map<String, Object>) result;
        return Map.of("result", result);
    }

    private static int detectJavaVersion() {
        String version = System.getProperty("java.version", "11");
        try {
            if (version.startsWith("1.")) {
                return Integer.parseInt(version.substring(2, 3));
            }
            int dotIndex = version.indexOf('.');
            if (dotIndex > 0) {
                return Integer.parseInt(version.substring(0, dotIndex));
            }
            return Integer.parseInt(version);
        } catch (NumberFormatException e) {
            return 11;
        }
    }
}
