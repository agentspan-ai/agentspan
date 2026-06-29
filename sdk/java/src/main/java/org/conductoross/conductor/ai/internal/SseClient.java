// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

import org.conductoross.conductor.ai.model.AgentEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import io.orkes.conductor.client.ApiClient;
import io.orkes.conductor.client.http.Pair;

import okhttp3.Call;
import okhttp3.Response;
import okhttp3.ResponseBody;

/**
 * Server-Sent Events (SSE) client for streaming agent events
 * ({@code GET /api/agent/stream/{executionId}}).
 *
 * <p>Streams through the shared native Conductor {@link ApiClient} — the request
 * is built with {@link ApiClient#buildCall} so it rides the SDK's OkHttp client
 * and token-refresh auth interceptor, exactly like every other client. The
 * response body is read incrementally; parsed events are placed into a
 * {@link LinkedBlockingQueue} and consumed via {@link #nextEvent()}.
 */
public class SseClient implements AutoCloseable {
    private static final Logger logger = LoggerFactory.getLogger(SseClient.class);

    /** Sentinel value to signal end-of-stream. */
    private static final AgentEvent DONE_SENTINEL = new AgentEvent(null, null, null, null, null, null, "", null, null);

    private final ApiClient apiClient;
    private final String executionId;
    private final BlockingQueue<AgentEvent> eventQueue = new LinkedBlockingQueue<>();
    private final AtomicBoolean closed = new AtomicBoolean(false);
    private volatile Call call;

    public SseClient(ApiClient apiClient, String executionId) {
        this.apiClient = apiClient;
        this.executionId = executionId;
    }

    /** Connect and start receiving SSE events in a background thread. */
    public void connect() {
        Thread streamThread = new Thread(this::streamLoop, "agentspan-sse-" + executionId);
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
            return event == DONE_SENTINEL ? null : event;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return null;
        }
    }

    @Override
    public void close() {
        closed.set(true);
        Call c = call;
        if (c != null) c.cancel();
        // Wake up any blocked nextEvent() calls
        eventQueue.offer(DONE_SENTINEL);
    }

    private void streamLoop() {
        StringBuilder dataBuffer = new StringBuilder();
        String[] eventTypeHolder = {null};

        try {
            Map<String, String> headers = new HashMap<>();
            headers.put("Accept", "text/event-stream");
            headers.put("Cache-Control", "no-cache");

            // Relative to the ApiClient's base path (the server's /api root); auth
            // and token refresh are applied by the client's OkHttp interceptor.
            call = apiClient.buildCall(
                    "/agent/stream/" + executionId,
                    "GET",
                    Collections.<Pair>emptyList(),
                    Collections.<Pair>emptyList(),
                    null,
                    headers);

            try (Response response = call.execute()) {
                if (!response.isSuccessful()) {
                    if (!closed.get()) {
                        logger.error("SSE connection failed with status {}", response.code());
                    }
                    return;
                }
                ResponseBody body = response.body();
                if (body == null) return;

                BufferedReader reader =
                        new BufferedReader(new InputStreamReader(body.byteStream(), StandardCharsets.UTF_8));
                String rawLine;
                while (!closed.get() && (rawLine = reader.readLine()) != null) {
                    // Strip trailing \r if present
                    String line = rawLine.endsWith("\r") ? rawLine.substring(0, rawLine.length() - 1) : rawLine;

                    if (line.isEmpty()) {
                        String data = dataBuffer.toString().trim();
                        if (!data.isEmpty()) dispatchEvent(eventTypeHolder[0], data);
                        dataBuffer.setLength(0);
                        eventTypeHolder[0] = null;
                        continue;
                    }
                    if (line.startsWith(":")) {
                        continue; // comment / heartbeat
                    }
                    if (line.startsWith("event:")) {
                        eventTypeHolder[0] = line.substring(6).trim();
                    } else if (line.startsWith("id:")) {
                        // Last event ID — tracked but not used currently
                    } else if (line.startsWith("data:")) {
                        String dataChunk = line.substring(5);
                        if (dataChunk.startsWith(" ")) dataChunk = dataChunk.substring(1);
                        if (dataBuffer.length() > 0) dataBuffer.append("\n");
                        dataBuffer.append(dataChunk);
                    }
                }

                // Dispatch any remaining buffered data
                String data = dataBuffer.toString().trim();
                if (!data.isEmpty()) dispatchEvent(eventTypeHolder[0], data);
            }
        } catch (Exception e) {
            if (!closed.get()) {
                logger.error("SSE stream error: {}", e.getMessage(), e);
            }
        } finally {
            eventQueue.offer(DONE_SENTINEL);
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
            if (event.getType() != null && "done".equals(event.getType().toJsonValue())) {
                eventQueue.offer(DONE_SENTINEL);
            }
        } catch (Exception e) {
            logger.warn("Failed to parse SSE event data: {} — {}", data, e.getMessage());
        }
    }
}
