// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.internal;

import dev.agentspan.AgentConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.lang.reflect.Method;
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
    private final HttpApi httpApi;
    private final ConcurrentHashMap<String, Function<Map<String, Object>, Object>> handlers;
    private ScheduledExecutorService scheduledExecutorService;
    private final ConcurrentHashMap<String, ScheduledFuture<?>> workerFutures;

    private static final int JAVA_VERSION = detectJavaVersion();

    public WorkerManager(AgentConfig config) {
        this.config = config;
        this.httpApi = new HttpApi(config);
        this.handlers = new ConcurrentHashMap<>();
        this.workerFutures = new ConcurrentHashMap<>();
    }

    /**
     * Register a task handler function for the given task name.
     *
     * @param taskName the Conductor task type name
     * @param handler  the function to call when a task is polled
     */
    public void register(String taskName, Function<Map<String, Object>, Object> handler) {
        if (handlers.containsKey(taskName)) {
            logger.debug("Re-registering existing handler for task: {}", taskName);
            handlers.put(taskName, handler);
            return;
        }
        handlers.put(taskName, handler);
        logger.info("Registered worker for task: {}", taskName);

        // Register task definition on the server
        try {
            httpApi.registerTaskDef(taskName);
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
            Map<String, Object> task = httpApi.pollTask(taskName);
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
            try {
                Object result = handler.apply(inputData);
                Map<String, Object> output = buildOutput(result);
                httpApi.completeTask(taskId, workflowInstanceId, output);
                logger.debug("Completed task {} ({})", taskName, taskId);
            } catch (Exception e) {
                logger.error("Task {} ({}) failed: {}", taskName, taskId, e.getMessage(), e);
                httpApi.failTask(taskId, workflowInstanceId, e.getMessage());
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
