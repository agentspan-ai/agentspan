// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.internal;

import dev.agentspan.AgentConfig;
import dev.agentspan.model.AgentEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Server-Sent Events (SSE) client for streaming agent events.
 *
 * <p>Uses {@code java.net.http.HttpClient} (Java 11+) for SSE streaming.
 * Events are placed into a {@code LinkedBlockingQueue} and consumed via
 * {@link #nextEvent()}.
 */
public class SseClient implements AutoCloseable {
    private static final Logger logger = LoggerFactory.getLogger(SseClient.class);

    /** Sentinel value to signal end-of-stream. */
    private static final AgentEvent DONE_SENTINEL = new AgentEvent(null, null, null, null, null, null, "", null, null);

    private final String url;
    private final AgentConfig config;
    private final HttpClient httpClient;
    private final BlockingQueue<AgentEvent> eventQueue = new LinkedBlockingQueue<>();
    private final AtomicBoolean closed = new AtomicBoolean(false);

    public SseClient(String url, AgentConfig config, HttpClient httpClient) {
        this.url = url;
        this.config = config;
        this.httpClient = httpClient;
    }

    /**
     * Connect and start receiving SSE events in a background thread.
     */
    public void connect() {
        Thread streamThread = new Thread(this::streamLoop, "agentspan-sse-" + url.hashCode());
        streamThread.setDaemon(true);
        streamThread.start();
    }

    /**
     * Block until the next event is available and return it.
     *
     * @return the next event, or null if the stream is done
     */
    public AgentEvent nextEvent() {
        try {
            AgentEvent event = eventQueue.take();
            if (event == DONE_SENTINEL) {
                return null;
            }
            return event;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return null;
        }
    }

    /**
     * Block with a timeout until the next event is available.
     *
     * @param timeout the timeout value
     * @param unit    the timeout unit
     * @return the next event, or null if timed out or done
     */
    public AgentEvent nextEvent(long timeout, TimeUnit unit) {
        try {
            AgentEvent event = eventQueue.poll(timeout, unit);
            if (event == null || event == DONE_SENTINEL) {
                return null;
            }
            return event;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return null;
        }
    }

    @Override
    public void close() {
        closed.set(true);
        // Wake up any blocked nextEvent() calls
        eventQueue.offer(DONE_SENTINEL);
    }

    private void streamLoop() {
        try {
            HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofMinutes(10))
                .GET()
                .header("Accept", "text/event-stream")
                .header("Cache-Control", "no-cache");

            if (config.getAuthKey() != null && !config.getAuthKey().isEmpty()) {
                requestBuilder.header("X-Auth-Key", config.getAuthKey());
            }
            if (config.getAuthSecret() != null && !config.getAuthSecret().isEmpty()) {
                requestBuilder.header("X-Auth-Secret", config.getAuthSecret());
            }

            HttpRequest request = requestBuilder.build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() >= 400) {
                logger.error("SSE connection failed with status {}", response.statusCode());
                eventQueue.offer(DONE_SENTINEL);
                return;
            }

            String body = response.body();
            if (body != null) {
                parseSSEBody(body);
            }

        } catch (Exception e) {
            if (!closed.get()) {
                logger.error("SSE stream error: {}", e.getMessage(), e);
            }
        } finally {
            eventQueue.offer(DONE_SENTINEL);
        }
    }

    /**
     * Parse the full SSE response body into events.
     * This handles the case where we get the complete body at once (non-chunked).
     */
    private void parseSSEBody(String body) {
        String[] lines = body.split("\n");
        StringBuilder dataBuffer = new StringBuilder();
        String eventType = null;

        for (String rawLine : lines) {
            if (closed.get()) break;

            // Remove trailing \r if present
            String line = rawLine.endsWith("\r") ? rawLine.substring(0, rawLine.length() - 1) : rawLine;

            if (line.isEmpty()) {
                // Blank line: dispatch accumulated event
                String data = dataBuffer.toString().trim();
                if (!data.isEmpty()) {
                    dispatchEvent(eventType, data);
                }
                dataBuffer.setLength(0);
                eventType = null;
                continue;
            }

            if (line.startsWith(":")) {
                // Comment / heartbeat — skip
                continue;
            }

            if (line.startsWith("event:")) {
                eventType = line.substring(6).trim();
            } else if (line.startsWith("id:")) {
                // Last event ID — tracked but not used currently
            } else if (line.startsWith("data:")) {
                String dataChunk = line.substring(5);
                if (dataChunk.startsWith(" ")) dataChunk = dataChunk.substring(1);
                if (dataBuffer.length() > 0) dataBuffer.append("\n");
                dataBuffer.append(dataChunk);
            }
        }

        // Dispatch any remaining data
        String data = dataBuffer.toString().trim();
        if (!data.isEmpty()) {
            dispatchEvent(eventType, data);
        }
    }

    @SuppressWarnings("unchecked")
    private void dispatchEvent(String eventType, String data) {
        try {
            if ("[DONE]".equals(data)) {
                eventQueue.offer(DONE_SENTINEL);
                return;
            }

            Map<String, Object> parsed = JsonMapper.fromJson(data, Map.class);
            AgentEvent event = AgentEvent.fromMap(parsed);

            eventQueue.offer(event);

            // Stop after DONE event
            if (event.getType() != null && "done".equals(event.getType().toJsonValue())) {
                eventQueue.offer(DONE_SENTINEL);
            }
        } catch (Exception e) {
            logger.warn("Failed to parse SSE event data: {} — {}", data, e.getMessage());
        }
    }
}
