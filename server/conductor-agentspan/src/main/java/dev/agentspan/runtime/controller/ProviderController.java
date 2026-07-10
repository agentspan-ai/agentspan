/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import dev.agentspan.runtime.ai.AgentspanAIModelProvider;

import lombok.RequiredArgsConstructor;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * Provider configuration status — the server-side source of truth.
 *
 * <p>Providers are configured on and dialed by the <b>server</b> (env at startup,
 * credential store, application.properties). Client-side tools like
 * {@code agentspan doctor} cannot know this from their own environment — a client
 * shell's {@code OPENAI_API_KEY} means nothing to a remote or containerized server.
 * This endpoint lets clients ask instead of guess.</p>
 *
 * <ul>
 *   <li>{@code GET /api/providers/status} — per-provider {@code configured} flag;
 *       for URL-based providers (ollama) also the resolved {@code baseUrl} and
 *       {@code reachable}, probed from the <b>server's</b> network.</li>
 * </ul>
 *
 * <p>When embedded in a host (e.g. orkes-conductor) the host owns provider
 * configuration, so the endpoint reports {@code managedByHost: true} and no
 * per-provider detail (mirrors {@code ProviderValidator}'s deference).
 * Delegating real per-provider status to the host via a
 * {@code ProviderStatusSource} SPI is tracked in
 * <a href="https://github.com/agentspan-ai/agentspan/issues/310">#310</a>;
 * the wire contract is forward-compatible ({@code managedByHost} stays,
 * {@code providers} fills in).</p>
 */
@RestController
@RequestMapping("/api/providers")
@RequiredArgsConstructor
public class ProviderController {

    /** Providers surfaced in status, aligned with the docs' provider list. */
    private static final List<String> KNOWN_PROVIDERS = List.of(
            "openai",
            "anthropic",
            "gemini",
            "azureopenai",
            "aws_bedrock",
            "mistral",
            "cohere",
            "grok",
            "perplexity",
            "huggingface",
            "ollama");

    private static final Duration PROBE_TIMEOUT = Duration.ofSeconds(2);

    private final AgentspanAIModelProvider modelProvider;
    private final OkHttpClient conductorAiHttpClient;
    private final Environment environment;

    @Value("${agentspan.embedded:false}")
    private boolean embedded;

    @GetMapping("/status")
    public Map<String, Object> status() {
        if (embedded) {
            return Map.of("managedByHost", true, "providers", List.of());
        }

        List<Map<String, Object>> providers = new ArrayList<>();
        for (String name : KNOWN_PROVIDERS) {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("name", name);
            entry.put("configured", modelProvider.isProviderConfigured(name));
            if ("ollama".equals(name)) {
                String baseUrl = modelProvider.resolveConfiguredBaseUrl("ollama");
                if (baseUrl == null) {
                    baseUrl = environment.getProperty("conductor.ai.ollama.base-url", "http://localhost:11434");
                }
                entry.put("baseUrl", baseUrl);
                entry.put("reachable", probe(baseUrl));
            }
            providers.add(entry);
        }
        return Map.of("managedByHost", false, "providers", providers);
    }

    /** Reachability from the server's own network — the fact no client can observe. */
    private boolean probe(String baseUrl) {
        try {
            OkHttpClient client = conductorAiHttpClient
                    .newBuilder()
                    .connectTimeout(PROBE_TIMEOUT)
                    .readTimeout(PROBE_TIMEOUT)
                    .callTimeout(PROBE_TIMEOUT.plusSeconds(1))
                    .build();
            Request request = new Request.Builder().url(baseUrl).get().build();
            try (Response ignored = client.newCall(request).execute()) {
                return true; // any HTTP response counts — the host is dialable
            }
        } catch (Exception e) {
            return false;
        }
    }
}
