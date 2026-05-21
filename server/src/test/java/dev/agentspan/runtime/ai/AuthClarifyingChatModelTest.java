/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.retry.NonTransientAiException;

import reactor.core.publisher.Flux;

/**
 * Unit tests for {@link AuthClarifyingChatModel}.
 *
 * <p>Wraps an upstream Spring AI {@link ChatModel}: when {@code call()} or
 * {@code stream()} fail with an authentication error (typically a 401 from
 * the provider), the wrapper rethrows as {@link IllegalStateException} with
 * a message naming the env var and remediation paths. Non-auth errors flow
 * through unchanged.</p>
 */
class AuthClarifyingChatModelTest {

    private static final Prompt PROMPT = new Prompt(new UserMessage("hello"));

    /** Tiny stub ChatModel whose call/stream behavior the test controls. */
    static class StubChatModel implements ChatModel {
        Throwable callError;
        Throwable streamError;
        ChatResponse callResult;
        Flux<ChatResponse> streamResult = Flux.empty();
        List<Prompt> callsReceived = new ArrayList<>();

        @Override
        public ChatResponse call(Prompt prompt) {
            callsReceived.add(prompt);
            if (callError != null) throwUnchecked(callError);
            return callResult;
        }

        @Override
        public Flux<ChatResponse> stream(Prompt prompt) {
            if (streamError != null) {
                return Flux.error(streamError);
            }
            return streamResult;
        }

        private static void throwUnchecked(Throwable t) {
            if (t instanceof RuntimeException re) throw re;
            throw new RuntimeException(t);
        }
    }

    private AuthClarifyingChatModel wrap(ChatModel delegate) {
        return new AuthClarifyingChatModel(delegate, "anthropic", "ANTHROPIC_API_KEY");
    }

    @Test
    void callRethrowsAuthErrorAsIllegalStateExceptionWithClearMessage() {
        StubChatModel stub = new StubChatModel();
        stub.callError = new NonTransientAiException("HTTP 401 Unauthorized: Invalid x-api-key");

        assertThatThrownBy(() -> wrap(stub).call(PROMPT))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("anthropic")
                .hasMessageContaining("ANTHROPIC_API_KEY");
    }

    @Test
    void callPassesNonAuthErrorsThrough() {
        StubChatModel stub = new StubChatModel();
        stub.callError = new RuntimeException("HTTP 500 Internal Server Error");

        assertThatThrownBy(() -> wrap(stub).call(PROMPT))
                .isInstanceOf(RuntimeException.class)
                // NOT wrapped — original exception bubbles up unchanged.
                .isNotInstanceOf(IllegalStateException.class)
                .hasMessage("HTTP 500 Internal Server Error");
    }

    @Test
    void callForwardsSuccessfulResponse() {
        StubChatModel stub = new StubChatModel();
        ChatResponse expected = new ChatResponse(List.of());
        stub.callResult = expected;

        ChatResponse actual = wrap(stub).call(PROMPT);

        assertThat(actual).isSameAs(expected);
        assertThat(stub.callsReceived).containsExactly(PROMPT);
    }

    @Test
    void streamMapsAuthErrorsMidStream() {
        StubChatModel stub = new StubChatModel();
        stub.streamError = new NonTransientAiException("401 Unauthorized");

        // blockLast() rethrows the terminal error from the Flux.
        assertThatThrownBy(() -> wrap(stub).stream(PROMPT).blockLast())
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("ANTHROPIC_API_KEY");
    }

    @Test
    void streamPassesNonAuthErrorsThrough() {
        StubChatModel stub = new StubChatModel();
        stub.streamError = new RuntimeException("HTTP 503");

        assertThatThrownBy(() -> wrap(stub).stream(PROMPT).blockLast())
                .isNotInstanceOf(IllegalStateException.class)
                .hasMessage("HTTP 503");
    }
}
