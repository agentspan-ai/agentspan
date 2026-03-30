/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import dev.agentspan.runtime.model.AgentSSEEvent;

/**
 * Manages SSE emitters and event buffers per agent execution.
 *
 * <p>Each execution ID maps to a list of connected {@link SseEmitter} instances
 * (multiple clients can watch the same execution). Events are buffered for
 * reconnection replay via {@code Last-Event-ID}.</p>
 */
@Component
public class AgentStreamRegistry {

    private static final Logger logger = LoggerFactory.getLogger(AgentStreamRegistry.class);
    private static final int DEFAULT_BUFFER_SIZE = 200;
    private static final long BUFFER_RETENTION_MS = 5 * 60 * 1000; // 5 minutes
    private static final long HEARTBEAT_INTERVAL_MS = 15_000; // 15 seconds

    /** Connected SSE emitters per execution ID. */
    private final ConcurrentHashMap<String, CopyOnWriteArrayList<SseEmitter>> emitters = new ConcurrentHashMap<>();

    /** Event buffer per execution ID (for replay on reconnect). */
    private final ConcurrentHashMap<String, BoundedEventBuffer> buffers = new ConcurrentHashMap<>();

    /** Child execution → parent execution aliases (for sub-workflow event forwarding). */
    private final ConcurrentHashMap<String, String> aliases = new ConcurrentHashMap<>();

    /** Per-execution monotonic event ID sequence. */
    private final ConcurrentHashMap<String, AtomicLong> sequences = new ConcurrentHashMap<>();

    /** Completed executions with their completion timestamp (for buffer cleanup). */
    private final ConcurrentHashMap<String, Long> completedAt = new ConcurrentHashMap<>();

    // ── Registration ─────────────────────────────────────────────────

    /**
     * Register a new SSE emitter for an execution. Replays missed events
     * if {@code lastEventId} is provided (reconnection scenario).
     */
    public SseEmitter register(String executionId, Long lastEventId) {
        // No timeout — lifecycle controlled by execution completion
        SseEmitter emitter = new SseEmitter(0L);

        emitters.computeIfAbsent(executionId, k -> new CopyOnWriteArrayList<>()).add(emitter);

        emitter.onCompletion(() -> removeEmitter(executionId, emitter));
        emitter.onTimeout(() -> removeEmitter(executionId, emitter));
        emitter.onError(e -> removeEmitter(executionId, emitter));

        // Send an initial comment to flush the HTTP response headers immediately.
        // Without this, some servlet containers buffer the response until the
        // first real event, causing the client to hang on connect.
        try {
            emitter.send(SseEmitter.event().comment("connected"));
        } catch (Exception e) {
            logger.warn("Failed to send initial SSE comment for execution {}: {}", executionId, e.getMessage());
        }

        // Replay missed events — on reconnect (lastEventId given) or first connect (replay all)
        BoundedEventBuffer buffer = buffers.get(executionId);
        if (buffer != null) {
            long sinceId = (lastEventId != null) ? lastEventId : 0;
            for (AgentSSEEvent event : buffer.eventsSince(sinceId)) {
                safeSend(emitter, event);
            }
        }

        logger.debug("Registered SSE emitter for execution {}", executionId);
        return emitter;
    }

    /**
     * Register a child execution as an alias for a parent execution.
     * Events from the child will be forwarded to the parent's SSE stream.
     */
    public void registerAlias(String childExecutionId, String parentExecutionId) {
        aliases.put(childExecutionId, parentExecutionId);
        logger.debug("Registered alias: {} → {}", childExecutionId, parentExecutionId);
    }

    // ── Event dispatch ───────────────────────────────────────────────

    /**
     * Send an event to all connected emitters for an execution.
     * Also buffers the event for reconnection replay.
     */
    public void send(String executionId, AgentSSEEvent event) {
        // Resolve alias (child → parent)
        String targetId = aliases.getOrDefault(executionId, executionId);

        // Assign monotonic sequence ID
        long seqId = sequences.computeIfAbsent(targetId, k -> new AtomicLong(0)).incrementAndGet();
        event.setId(seqId);

        // Buffer the event
        buffers.computeIfAbsent(targetId, k -> new BoundedEventBuffer(DEFAULT_BUFFER_SIZE))
                .add(event);

        // Broadcast to all connected emitters
        CopyOnWriteArrayList<SseEmitter> list = emitters.get(targetId);
        if (list != null) {
            for (SseEmitter emitter : list) {
                safeSend(emitter, event);
            }
        }
    }

    /**
     * Mark an execution as complete. Completes all emitters and schedules
     * buffer cleanup.
     */
    public void complete(String executionId) {
        String targetId = aliases.getOrDefault(executionId, executionId);

        CopyOnWriteArrayList<SseEmitter> list = emitters.remove(targetId);
        if (list != null) {
            for (SseEmitter emitter : list) {
                try {
                    emitter.complete();
                } catch (Exception ignored) {
                }
            }
        }

        // Mark for buffer cleanup after retention period
        completedAt.put(targetId, System.currentTimeMillis());

        // Clean up aliases pointing to this execution
        aliases.entrySet().removeIf(e -> e.getValue().equals(targetId));

        logger.debug("Completed SSE stream for execution {}", targetId);
    }

    /**
     * Check if any emitters are registered for an execution.
     */
    public boolean hasListeners(String executionId) {
        String targetId = aliases.getOrDefault(executionId, executionId);
        CopyOnWriteArrayList<SseEmitter> list = emitters.get(targetId);
        return list != null && !list.isEmpty();
    }

    // ── Heartbeat ────────────────────────────────────────────────────

    /**
     * Send heartbeat comments to all open SSE connections to prevent
     * proxy/load-balancer idle timeouts.
     */
    @Scheduled(fixedRate = HEARTBEAT_INTERVAL_MS)
    public void sendHeartbeats() {
        for (Map.Entry<String, CopyOnWriteArrayList<SseEmitter>> entry : emitters.entrySet()) {
            for (SseEmitter emitter : entry.getValue()) {
                try {
                    emitter.send(SseEmitter.event().comment("heartbeat"));
                } catch (IOException e) {
                    removeEmitter(entry.getKey(), emitter);
                }
            }
        }
    }

    // ── Cleanup ──────────────────────────────────────────────────────

    /**
     * Periodically clean up stale event buffers and sequences for
     * executions that completed more than {@code BUFFER_RETENTION_MS} ago.
     */
    @Scheduled(fixedRate = 60_000) // every minute
    public void cleanupStaleBuffers() {
        long now = System.currentTimeMillis();
        completedAt.entrySet().removeIf(entry -> {
            if (now - entry.getValue() > BUFFER_RETENTION_MS) {
                String execId = entry.getKey();
                buffers.remove(execId);
                sequences.remove(execId);
                logger.debug("Cleaned up buffer for execution {}", execId);
                return true;
            }
            return false;
        });
    }

    // ── Shutdown ─────────────────────────────────────────────────────

    /**
     * Complete all open SSE emitters. Called during application shutdown
     * so Tomcat request threads are released and the JVM can exit.
     */
    public void completeAll() {
        for (Map.Entry<String, CopyOnWriteArrayList<SseEmitter>> entry : emitters.entrySet()) {
            for (SseEmitter emitter : entry.getValue()) {
                try {
                    emitter.complete();
                } catch (Exception ignored) {
                }
            }
        }
        emitters.clear();
        logger.info("Completed all SSE emitters for shutdown");
    }

    // ── Internal ─────────────────────────────────────────────────────

    private void removeEmitter(String executionId, SseEmitter emitter) {
        CopyOnWriteArrayList<SseEmitter> list = emitters.get(executionId);
        if (list != null) {
            list.remove(emitter);
            if (list.isEmpty()) {
                emitters.remove(executionId);
            }
        }
    }

    private void safeSend(SseEmitter emitter, AgentSSEEvent event) {
        try {
            emitter.send(SseEmitter.event()
                    .id(String.valueOf(event.getId()))
                    .name(event.getType())
                    .data(event.toJson()));
        } catch (Exception e) {
            // Client disconnected — will be cleaned up by onError/onCompletion
        }
    }

    // ── Bounded event buffer ─────────────────────────────────────────

    static class BoundedEventBuffer {
        private final int maxSize;
        private final LinkedList<AgentSSEEvent> events = new LinkedList<>();

        BoundedEventBuffer(int maxSize) {
            this.maxSize = maxSize;
        }

        synchronized void add(AgentSSEEvent event) {
            events.addLast(event);
            while (events.size() > maxSize) {
                events.removeFirst();
            }
        }

        synchronized List<AgentSSEEvent> eventsSince(long lastEventId) {
            List<AgentSSEEvent> result = new ArrayList<>();
            for (AgentSSEEvent event : events) {
                if (event.getId() > lastEventId) {
                    result.add(event);
                }
            }
            return result;
        }
    }
}
