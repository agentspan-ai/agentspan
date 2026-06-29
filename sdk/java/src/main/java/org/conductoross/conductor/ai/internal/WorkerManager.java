// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

import org.conductoross.conductor.ai.AgentConfig;
import org.conductoross.conductor.ai.exceptions.CredentialAuthException;
import org.conductoross.conductor.ai.exceptions.CredentialNotFoundException;
import org.conductoross.conductor.ai.exceptions.CredentialRateLimitException;
import org.conductoross.conductor.ai.exceptions.CredentialServiceException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.netflix.conductor.client.automator.TaskRunnerConfigurer;
import com.netflix.conductor.client.http.ConductorClient;
import com.netflix.conductor.client.http.MetadataClient;
import com.netflix.conductor.client.http.TaskClient;
import com.netflix.conductor.client.worker.Worker;
import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.common.metadata.tasks.TaskDef;
import com.netflix.conductor.common.metadata.tasks.TaskResult;

/**
 * Manages worker task handlers and drives them with the official Conductor
 * client ({@link TaskRunnerConfigurer} + {@link Worker}).
 *
 * <p>Replaces the previous hand-rolled poll loop. The Conductor client provides
 * battle-tested task polling, backoff, managed worker threads, and — crucially —
 * automatic <b>lease extension (heartbeat)</b> for in-flight tasks (every worker
 * here returns {@code leaseExtendEnabled() == true}). A handler that blocks for
 * minutes keeps its lease alive instead of being reclaimed and re-dispatched.
 *
 * <p>Agentspan registers workers incrementally (per run, sometimes under a
 * per-execution domain), whereas a {@link TaskRunnerConfigurer} is built from a
 * fixed worker set. We bridge the two models by (re)building the configurer in
 * {@link #startAll()} whenever a <i>new</i> task type has been registered since
 * the last build. The common cases — {@code serve()} and repeated runs of the
 * same agent — build exactly once; re-registering an existing task only swaps the
 * handler (looked up live in {@link Worker#execute}) and needs no rebuild.
 *
 * <p>What is preserved from the old implementation: per-task worker domains
 * ({@link TaskRunnerConfigurer.Builder#withTaskToDomain}), declared-credential
 * resolution before each handler call (with terminal failure on credential
 * errors so Conductor doesn't burn retries), and the {@code result → outputData}
 * mapping.
 */
public class WorkerManager {
    private static final Logger logger = LoggerFactory.getLogger(WorkerManager.class);

    /**
     * Minimum threads per worker type in the shared pool. Each worker type needs at least one
     * thread to make progress, so the actual floor is {@code max(MIN_THREADS_PER_WORKER × N, configured)}.
     * Keeping this at 1 means the configured {@link AgentConfig#getWorkerThreadCount()} is always
     * respected (a test can set 1; production callers set higher).
     */
    private static final int MIN_THREADS_PER_WORKER = 1;

    /** Default task-def timeout (seconds) for handlers with no configured timeout. */
    static final int DEFAULT_TASK_TIMEOUT_SECONDS = 300;

    /**
     * Slack added on top of a handler's configured timeout so the server's
     * patience always exceeds the worker's blocking duration — covering process
     * kill/teardown (e.g. Docker's {@code timeout + 10}s) plus the task-update
     * round-trip. With lease extension this is belt-and-suspenders, but it keeps
     * the registered task def honest.
     */
    static final int TASK_TIMEOUT_SLACK_SECONDS = 60;

    /**
     * Effective task-def timeout for a handler that blocks up to
     * {@code configuredSeconds}. Floors at {@link #DEFAULT_TASK_TIMEOUT_SECONDS}
     * so short tasks keep the proven-safe default, and only ever raises the
     * ceiling for genuinely long-running handlers — the server's
     * {@code responseTimeoutSeconds} can never drift below the handler's timeout.
     */
    static int effectiveTaskTimeout(int configuredSeconds) {
        if (configuredSeconds <= 0) return DEFAULT_TASK_TIMEOUT_SECONDS;
        return Math.max(DEFAULT_TASK_TIMEOUT_SECONDS, configuredSeconds + TASK_TIMEOUT_SLACK_SECONDS);
    }

    private final AgentConfig config;
    private final WorkerCredentialFetcher credentialFetcher;
    private final TaskClient taskClient;
    private final MetadataClient metadataClient;

    private final ConcurrentHashMap<String, Function<Map<String, Object>, Object>> handlers;
    /** Optional worker domain per task name. Tasks without an entry poll the default queue. */
    private final ConcurrentHashMap<String, String> taskDomains;
    /** Declared credential names per task name. Empty list when no secrets are declared. */
    private final ConcurrentHashMap<String, List<String>> taskCredentials;

    /**
     * Domain applied by the no-arg {@link #register(String, Function)} overload.
     * AgentRuntime sets this for the lifetime of a single
     * {@code prepareWorkers(agent, domain)} call so all subsequent register
     * calls register under the same per-execution domain.
     */
    private volatile String currentDomain;

    private final Object lifecycleLock = new Object();
    private TaskRunnerConfigurer configurer;
    /** True when a new task type was registered since the last configurer build. */
    private boolean workerSetChanged;

    public WorkerManager(AgentConfig config, ConductorClient conductorClient) {
        this.config = config;
        this.credentialFetcher = new WorkerCredentialFetcher(conductorClient);
        this.handlers = new ConcurrentHashMap<>();
        this.taskDomains = new ConcurrentHashMap<>();
        this.taskCredentials = new ConcurrentHashMap<>();

        // Worker protocol via the shared native Conductor client.
        this.taskClient = new TaskClient(conductorClient);
        this.metadataClient = new MetadataClient(conductorClient);
    }

    // ── Registration ───────────────────────────────────────────────────────

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
     */
    public void setCurrentDomain(String domain) {
        this.currentDomain = domain;
    }

    /** Read the domain set by the most recent {@link #setCurrentDomain(String)}. */
    public String getCurrentDomain() {
        return currentDomain;
    }

    // ── Test hooks (package-private) ─────────────────────────────────────────

    /** Visible for testing: the thread count that would be used if startAll() were called now. */
    int computeThreadCount() {
        return Math.max(config.getWorkerThreadCount(), MIN_THREADS_PER_WORKER * handlers.size());
    }

    /** Visible for testing: the domain a task is currently registered under (or null). */
    String getTaskDomain(String taskName) {
        return taskDomains.get(taskName);
    }

    /** Visible for testing: whether a runner (re)build is pending. */
    boolean isWorkerSetChanged() {
        synchronized (lifecycleLock) {
            return workerSetChanged;
        }
    }

    /** Visible for testing: simulate {@link #startAll()} having consumed the change flag. */
    void clearWorkerSetChangedForTest() {
        synchronized (lifecycleLock) {
            workerSetChanged = false;
        }
    }

    public void register(String taskName, Function<Map<String, Object>, Object> handler, String domain) {
        register(taskName, handler, domain, Collections.emptyList());
    }

    public void register(
            String taskName, Function<Map<String, Object>, Object> handler, String domain, List<String> credentials) {
        register(taskName, handler, domain, credentials, 0);
    }

    /**
     * Register a task handler whose Conductor task-def timeout tracks the
     * handler's configured blocking timeout.
     *
     * <p>{@code taskTimeoutSeconds} is the handler's max blocking time (e.g.
     * {@code CliConfig.timeout}, the code-execution timeout, or a worker tool's
     * {@code timeoutSeconds}). The registered task def's
     * {@code responseTimeoutSeconds} is set to {@link #effectiveTaskTimeout}
     * of it, so the server's patience never drifts below the handler's timeout
     * (and, combined with lease extension, a long task is not reclaimed
     * mid-flight). Pass {@code 0} for the default.
     */
    public void register(
            String taskName,
            Function<Map<String, Object>, Object> handler,
            String domain,
            List<String> credentials,
            int taskTimeoutSeconds) {
        boolean isNew = !handlers.containsKey(taskName);
        String previousDomain = taskDomains.get(taskName);
        handlers.put(taskName, handler);

        String normalizedDomain = (domain != null && !domain.isEmpty()) ? domain : null;
        if (normalizedDomain != null) {
            taskDomains.put(taskName, normalizedDomain);
        } else {
            taskDomains.remove(taskName);
        }
        if (credentials != null && !credentials.isEmpty()) {
            taskCredentials.put(taskName, List.copyOf(credentials));
        } else {
            taskCredentials.remove(taskName);
        }

        if (!isNew) {
            // Same task type — the Worker looks the handler up live, so a swapped
            // handler takes effect with no rebuild. BUT the domain is baked into the
            // running configurer's taskToDomain at build time, so a *changed* domain
            // (e.g. a stateful run's per-execution runId registered after a prior
            // no-domain registration) requires a rebuild — otherwise the worker keeps
            // polling the old/default queue while the server enqueues the task under
            // the new domain, and the task sits SCHEDULED until the run times out.
            if (!Objects.equals(previousDomain, normalizedDomain)) {
                synchronized (lifecycleLock) {
                    workerSetChanged = true;
                }
                logger.info(
                        "Re-registered worker for task {} under new domain {} (was {})",
                        taskName,
                        normalizedDomain,
                        previousDomain);
            } else {
                logger.debug("Re-registered handler for task: {} (domain={})", taskName, domain);
            }
            return;
        }

        // Size and upsert the task def so the server's timeouts track the handler.
        registerTaskDef(taskName, taskTimeoutSeconds);

        synchronized (lifecycleLock) {
            workerSetChanged = true;
        }
        logger.info("Registered worker for task: {} (domain={})", taskName, domain);
    }

    private void registerTaskDef(String taskName, int configuredTimeoutSeconds) {
        try {
            long timeout = effectiveTaskTimeout(configuredTimeoutSeconds);
            TaskDef taskDef = new TaskDef(taskName);
            taskDef.setTimeoutSeconds(timeout);
            taskDef.setResponseTimeoutSeconds(timeout);
            metadataClient.registerTaskDefs(List.of(taskDef));
        } catch (Exception e) {
            logger.debug("Could not register task def {} (may already exist): {}", taskName, e.getMessage());
        }
    }

    // ── Lifecycle ──────────────────────────────────────────────────────────

    /**
     * Start (or rebuild) the Conductor task runner for all registered workers.
     * Idempotent: returns immediately when no new task type has been registered
     * since the last build.
     */
    public void startAll() {
        synchronized (lifecycleLock) {
            if (configurer != null && !workerSetChanged) {
                return; // already running, nothing new to add
            }
            if (handlers.isEmpty()) {
                return; // nothing to run yet
            }

            if (configurer != null) {
                // A new task type appeared — rebuild with the full worker set.
                try {
                    configurer.shutdown();
                } catch (Exception e) {
                    logger.debug("Error shutting down previous task runner: {}", e.getMessage());
                }
                configurer = null;
            }

            List<Worker> workers = new ArrayList<>();
            for (String taskName : handlers.keySet()) {
                workers.add(makeWorker(taskName));
            }

            Map<String, String> taskToDomain = new HashMap<>();
            for (Map.Entry<String, String> e : taskDomains.entrySet()) {
                if (e.getValue() != null && !e.getValue().isEmpty()) {
                    taskToDomain.put(e.getKey(), e.getValue());
                }
            }

            // Need at least 1 thread per worker type (otherwise a blocking handler starves others),
            // but respect the configured count — don't silently override an explicit setting.
            int threadCount = Math.max(config.getWorkerThreadCount(), MIN_THREADS_PER_WORKER * workers.size());

            TaskRunnerConfigurer.Builder builder = new TaskRunnerConfigurer.Builder(taskClient, workers)
                    .withThreadCount(threadCount)
                    .withWorkerNamePrefix("agentspan-worker-");
            if (!taskToDomain.isEmpty()) {
                builder.withTaskToDomain(taskToDomain);
            }

            configurer = builder.build();
            configurer.init();
            workerSetChanged = false;
            logger.info("Started Conductor task runner: {} worker(s), {} thread(s)", workers.size(), threadCount);
        }
    }

    /** Stop the Conductor task runner. */
    public void stop() {
        synchronized (lifecycleLock) {
            if (configurer != null) {
                try {
                    configurer.shutdown();
                } catch (Exception e) {
                    logger.debug("Error during task runner shutdown: {}", e.getMessage());
                }
                configurer = null;
            }
        }
    }

    // ── Worker ─────────────────────────────────────────────────────────────

    /**
     * Build a Conductor {@link Worker} for {@code taskName}. The handler is
     * looked up live so a re-registered handler takes effect without a rebuild.
     */
    private Worker makeWorker(String taskName) {
        return new Worker() {
            @Override
            public String getTaskDefName() {
                return taskName;
            }

            @Override
            public int getPollingInterval() {
                return config.getWorkerPollIntervalMs();
            }

            @Override
            public boolean leaseExtendEnabled() {
                // Heartbeat: keep a long-running task's lease alive so the server
                // does not reclaim and re-dispatch it while the handler blocks.
                return true;
            }

            @Override
            public TaskResult execute(Task task) {
                return executeHandler(taskName, task);
            }
        };
    }

    private TaskResult executeHandler(String taskName, Task task) {
        TaskResult result = new TaskResult(task);
        Map<String, Object> inputData = task.getInputData() != null ? task.getInputData() : Collections.emptyMap();

        // Resolve declared secrets BEFORE invoking the handler. Credential
        // failures are terminal so Conductor doesn't burn retries on a config
        // problem. See docs/design/secret-injection-contract.md.
        Map<String, String> resolvedSecrets = Collections.emptyMap();
        List<String> declared = taskCredentials.getOrDefault(taskName, Collections.emptyList());
        if (!declared.isEmpty()) {
            String execToken = extractExecutionToken(inputData);
            try {
                resolvedSecrets = credentialFetcher.fetch(execToken, declared);
            } catch (CredentialNotFoundException
                    | CredentialAuthException
                    | CredentialRateLimitException
                    | CredentialServiceException ce) {
                logger.error(
                        "Credential resolution failed for task {} ({}): {}",
                        taskName,
                        task.getTaskId(),
                        ce.getMessage());
                result.setStatus(TaskResult.Status.FAILED_WITH_TERMINAL_ERROR);
                result.setReasonForIncompletion("Credential resolution failed: " + ce.getMessage());
                return result;
            }
        }

        Function<Map<String, Object>, Object> handler = handlers.get(taskName);
        if (handler == null) {
            result.setStatus(TaskResult.Status.FAILED);
            result.setReasonForIncompletion("No handler registered for task " + taskName);
            return result;
        }

        try {
            CredentialContext.set(resolvedSecrets);
            try {
                Object out = handler.apply(inputData);
                result.setStatus(TaskResult.Status.COMPLETED);
                result.setOutputData(buildOutput(out));
                logger.debug("Completed task {} ({})", taskName, task.getTaskId());
            } finally {
                CredentialContext.clear();
            }
        } catch (Exception e) {
            logger.error("Task {} ({}) failed: {}", taskName, task.getTaskId(), e.getMessage(), e);
            result.setStatus(TaskResult.Status.FAILED);
            result.setReasonForIncompletion(e.getMessage());
        }
        return result;
    }

    /**
     * Pull the execution token out of {@code inputData["__agentspan_ctx__"]["execution_token"]}.
     * Returns {@code null} if no token is present.
     */
    @SuppressWarnings("unchecked")
    private static String extractExecutionToken(Map<String, Object> inputData) {
        if (inputData == null) return null;
        Object ctx = inputData.get("__agentspan_ctx__");
        if (!(ctx instanceof Map<?, ?> ctxMap)) return null;
        Object token = ctxMap.get("execution_token");
        if (token == null) token = ctxMap.get("executionToken"); // tolerate camelCase
        return token instanceof String s ? s : null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> buildOutput(Object result) {
        if (result == null) return Map.of();
        if (result instanceof Map) return (Map<String, Object>) result;
        return Map.of("result", result);
    }
}
