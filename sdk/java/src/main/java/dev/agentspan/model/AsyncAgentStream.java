// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;

/**
 * Async wrapper around {@link AgentStream} that integrates with {@link CompletableFuture}.
 *
 * <pre>{@code
 * CompletableFuture<AsyncAgentStream> future = runtime.streamAsync(agent, "Hello");
 * AsyncAgentStream stream = future.join();
 * stream.onEvent(event -> System.out.println(event.getType() + ": " + event.getData()))
 *       .onComplete(result -> System.out.println("Done: " + result.getOutput()))
 *       .await();
 * }</pre>
 */
public class AsyncAgentStream {

    private final CompletableFuture<AgentStream> streamFuture;
    private Consumer<AgentEvent> eventHandler;
    private Consumer<AgentResult> completeHandler;
    private Consumer<Throwable> errorHandler;

    public AsyncAgentStream(CompletableFuture<AgentStream> streamFuture) {
        this.streamFuture = streamFuture;
    }

    /** Register a handler for each streaming event. */
    public AsyncAgentStream onEvent(Consumer<AgentEvent> handler) {
        this.eventHandler = handler;
        return this;
    }

    /** Register a handler called when the stream completes. */
    public AsyncAgentStream onComplete(Consumer<AgentResult> handler) {
        this.completeHandler = handler;
        return this;
    }

    /** Register a handler called on errors. */
    public AsyncAgentStream onError(Consumer<Throwable> handler) {
        this.errorHandler = handler;
        return this;
    }

    /** Block until the stream completes and return the final AgentResult. */
    public AgentResult await() {
        try {
            AgentStream stream = streamFuture.join();
            if (eventHandler != null) {
                for (AgentEvent event : stream) {
                    eventHandler.accept(event);
                }
            }
            AgentResult result = stream.getResult();
            if (completeHandler != null) {
                completeHandler.accept(result);
            }
            return result;
        } catch (Exception e) {
            if (errorHandler != null) {
                errorHandler.accept(e);
                return null;
            }
            throw e;
        }
    }

    /** The underlying CompletableFuture. */
    public CompletableFuture<AgentStream> toFuture() {
        return streamFuture;
    }
}
