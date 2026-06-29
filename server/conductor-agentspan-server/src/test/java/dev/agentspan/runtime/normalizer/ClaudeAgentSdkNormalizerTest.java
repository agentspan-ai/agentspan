/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import static org.assertj.core.api.Assertions.*;

import java.util.Map;

import org.junit.jupiter.api.Test;

import dev.agentspan.runtime.model.AgentConfig;

class ClaudeAgentSdkNormalizerTest {

    private final ClaudeAgentSdkNormalizer normalizer = new ClaudeAgentSdkNormalizer();

    @Test
    void frameworkIdIsClaudeAgentSdk() {
        assertThat(normalizer.frameworkId()).isEqualTo("claude_agent_sdk");
    }

    @Test
    void normalizeProducesPassthroughConfig() {
        Map<String, Object> raw = Map.of(
                "name", "my_agent",
                "_worker_name", "my_agent");

        AgentConfig config = normalizer.normalize(raw);

        assertThat(config.getName()).isEqualTo("my_agent");
        assertThat(config.getModel()).isNull();
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
        assertThat(config.getTools()).hasSize(1);
        assertThat(config.getTools().get(0).getName()).isEqualTo("my_agent");
        assertThat(config.getTools().get(0).getToolType()).isEqualTo("worker");
    }

    @Test
    void normalizeUsesDefaultNameWhenMissing() {
        AgentConfig config = normalizer.normalize(Map.of());

        assertThat(config.getName()).isEqualTo("claude_agent_sdk_agent");
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
    }
}
