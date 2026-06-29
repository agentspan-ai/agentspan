/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import java.util.Map;

import dev.agentspan.runtime.model.AgentConfig;

/**
 * Normalizes a framework-specific raw agent config into the canonical {@link AgentConfig}.
 *
 * <p>Implementations are auto-discovered by Spring as {@code @Component} beans and
 * registered in {@link NormalizerRegistry} by their {@link #frameworkId()}.
 */
public interface AgentConfigNormalizer {

    /** The framework identifier this normalizer handles (e.g. "openai", "google_adk"). */
    String frameworkId();

    /**
     * Convert a framework-native agent config (as deserialized JSON) into the
     * canonical {@link AgentConfig} understood by {@link dev.agentspan.runtime.compiler.AgentCompiler}.
     *
     * @param rawConfig the framework-specific agent definition as a Map
     * @return the normalized AgentConfig
     */
    AgentConfig normalize(Map<String, Object> rawConfig);
}
