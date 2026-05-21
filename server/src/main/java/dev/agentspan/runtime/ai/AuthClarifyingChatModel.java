/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.chat.prompt.Prompt;

import reactor.core.publisher.Flux;

/**
 * Delegating {@link ChatModel} that translates upstream provider
 * authentication failures into a clear {@link IllegalStateException}.
 *
 * <p>Catches both synchronous (from {@link #call}) and reactive (from
 * {@link #stream}) auth errors using {@link AuthErrorMessageMapper}.
 * Non-auth errors are passed through unchanged.</p>
 */
final class AuthClarifyingChatModel implements ChatModel {

    private final ChatModel delegate;
    private final String provider;
    private final String envVar;

    AuthClarifyingChatModel(ChatModel delegate, String provider, String envVar) {
        this.delegate = delegate;
        this.provider = provider;
        this.envVar = envVar;
    }

    @Override
    public ChatResponse call(Prompt prompt) {
        try {
            return delegate.call(prompt);
        } catch (RuntimeException e) {
            if (AuthErrorMessageMapper.isAuthFailure(e)) {
                throw new IllegalStateException(
                        AuthErrorMessageMapper.buildMessage(provider, envVar), e);
            }
            throw e;
        }
    }

    @Override
    public Flux<ChatResponse> stream(Prompt prompt) {
        Flux<ChatResponse> upstream;
        try {
            upstream = delegate.stream(prompt);
        } catch (RuntimeException e) {
            if (AuthErrorMessageMapper.isAuthFailure(e)) {
                throw new IllegalStateException(
                        AuthErrorMessageMapper.buildMessage(provider, envVar), e);
            }
            throw e;
        }
        return upstream.onErrorMap(
                AuthErrorMessageMapper::isAuthFailure,
                e -> new IllegalStateException(
                        AuthErrorMessageMapper.buildMessage(provider, envVar), e));
    }

    @Override
    public ChatOptions getDefaultOptions() {
        return delegate.getDefaultOptions();
    }
}
