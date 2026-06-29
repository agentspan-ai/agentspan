/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import static org.assertj.core.api.Assertions.*;

import java.util.Map;

import org.junit.jupiter.api.Test;

import dev.agentspan.runtime.model.AgentConfig;

class LangChainNormalizerTest {

    private final LangChainNormalizer normalizer = new LangChainNormalizer();

    @Test
    void frameworkIdIsLangchain() {
        assertThat(normalizer.frameworkId()).isEqualTo("langchain");
    }

    @Test
    void normalizeProducesPassthroughConfig() {
        Map<String, Object> raw = Map.of(
                "name", "my_executor",
                "_worker_name", "my_executor");

        AgentConfig config = normalizer.normalize(raw);

        assertThat(config.getName()).isEqualTo("my_executor");
        assertThat(config.getModel()).isNull();
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
        assertThat(config.getTools()).hasSize(1);
        assertThat(config.getTools().get(0).getName()).isEqualTo("my_executor");
        assertThat(config.getTools().get(0).getToolType()).isEqualTo("worker");
    }

    @Test
    void normalizeUsesDefaultNameWhenMissing() {
        AgentConfig config = normalizer.normalize(Map.of());

        assertThat(config.getName()).isEqualTo("langchain_agent");
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
    }
}
