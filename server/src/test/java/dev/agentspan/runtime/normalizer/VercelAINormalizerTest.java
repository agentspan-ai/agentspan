/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.assertj.core.api.Assertions.*;

class VercelAINormalizerTest {

    private final VercelAINormalizer normalizer = new VercelAINormalizer();

    @Test
    void testFrameworkId() {
        assertThat(normalizer.frameworkId()).isEqualTo("vercel_ai");
    }

    @Test
    void testNormalizeWithDefaults() {
        AgentConfig config = normalizer.normalize(Map.of());

        assertThat(config.getName()).isEqualTo("vercel_ai_agent");
        assertThat(config.getModel()).isNull();
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
        assertThat(config.getTools()).hasSize(1);
        assertThat(config.getTools().get(0).getName()).isEqualTo("vercel_ai_agent");
        assertThat(config.getTools().get(0).getToolType()).isEqualTo("worker");
    }

    @Test
    void testNormalizeWithCustomName() {
        AgentConfig config = normalizer.normalize(Map.of("name", "my_vercel_agent"));

        assertThat(config.getName()).isEqualTo("my_vercel_agent");
        // Worker name defaults to agent name when _worker_name is absent
        assertThat(config.getTools().get(0).getName()).isEqualTo("my_vercel_agent");
    }

    @Test
    void testNormalizeWithWorkerName() {
        AgentConfig config = normalizer.normalize(Map.of(
            "name", "my_vercel_agent",
            "_worker_name", "custom_worker"
        ));

        assertThat(config.getName()).isEqualTo("my_vercel_agent");
        assertThat(config.getTools().get(0).getName()).isEqualTo("custom_worker");
    }

    @Test
    void testNormalizePassthroughMetadata() {
        AgentConfig config = normalizer.normalize(Map.of("name", "test_agent"));

        assertThat(config.getMetadata()).isNotNull();
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
    }

    @Test
    void testNormalizeToolConfig() {
        AgentConfig config = normalizer.normalize(Map.of(
            "name", "test_agent",
            "_worker_name", "test_agent"
        ));

        assertThat(config.getTools()).hasSize(1);
        assertThat(config.getTools().get(0).getToolType()).isEqualTo("worker");
        assertThat(config.getTools().get(0).getName()).isEqualTo("test_agent");
        assertThat(config.getTools().get(0).getDescription()).isEqualTo("Vercel AI SDK passthrough worker");
    }
}
