/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import java.util.List;

import org.conductoross.conductor.ai.AIModel;
import org.conductoross.conductor.ai.models.AudioGenRequest;
import org.conductoross.conductor.ai.models.ChatCompletion;
import org.conductoross.conductor.ai.models.EmbeddingGenRequest;
import org.conductoross.conductor.ai.models.ImageGenRequest;
import org.conductoross.conductor.ai.models.LLMResponse;
import org.conductoross.conductor.ai.models.VideoGenRequest;
import org.conductoross.conductor.ai.video.VideoModel;
import org.conductoross.conductor.ai.video.VideoOptions;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.image.ImageModel;
import org.springframework.ai.image.ImageOptions;
import org.springframework.ai.tool.ToolCallback;

/**
 * Delegating {@link AIModel} that returns an {@link AuthClarifyingChatModel}
 * from {@link #getChatModel()}. All other methods forward to the wrapped
 * model. Used in {@link AgentspanAIModelProvider#createModelWithKey} to
 * surface clear errors when a non-empty but invalid API key is rejected
 * by the upstream provider.
 */
final class AuthClarifyingAIModel implements AIModel {

    private final AIModel delegate;
    private final String provider;
    private final String envVar;

    AuthClarifyingAIModel(AIModel delegate, String provider, String envVar) {
        this.delegate = delegate;
        this.provider = provider;
        this.envVar = envVar;
    }

    @Override
    public ChatModel getChatModel() {
        return new AuthClarifyingChatModel(delegate.getChatModel(), provider, envVar);
    }

    // ── pure delegation ───────────────────────────────────────────────

    @Override
    public String getModelProvider() {
        return delegate.getModelProvider();
    }

    @Override
    public List<String> getProviderAliases() {
        return delegate.getProviderAliases();
    }

    @Override
    public List<Float> generateEmbeddings(EmbeddingGenRequest request) {
        return delegate.generateEmbeddings(request);
    }

    @Override
    public ChatOptions getChatOptions(ChatCompletion input) {
        return delegate.getChatOptions(input);
    }

    @Override
    public ImageOptions getImageOptions(ImageGenRequest input) {
        return delegate.getImageOptions(input);
    }

    @Override
    public ImageModel getImageModel() {
        return delegate.getImageModel();
    }

    @Override
    public VideoOptions getVideoOptions(VideoGenRequest input) {
        return delegate.getVideoOptions(input);
    }

    @Override
    public VideoModel getVideoModel() {
        return delegate.getVideoModel();
    }

    @Override
    public LLMResponse generateVideo(VideoGenRequest request) {
        return delegate.generateVideo(request);
    }

    @Override
    public LLMResponse checkVideoStatus(VideoGenRequest request) {
        return delegate.checkVideoStatus(request);
    }

    @Override
    public LLMResponse generateAudio(AudioGenRequest request) {
        return delegate.generateAudio(request);
    }

    @Override
    public List<ToolCallback> getToolCallback(ChatCompletion input) {
        return delegate.getToolCallback(input);
    }
}
