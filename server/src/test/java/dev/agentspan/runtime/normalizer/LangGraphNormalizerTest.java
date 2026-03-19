/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.assertj.core.api.Assertions.*;

class LangGraphNormalizerTest {

    private final LangGraphNormalizer normalizer = new LangGraphNormalizer();

    @Test
    void frameworkIdIsLanggraph() {
        assertThat(normalizer.frameworkId()).isEqualTo("langgraph");
    }

    @Test
    void normalizeProducesPassthroughConfig() {
        Map<String, Object> raw = Map.of(
            "name", "my_graph",
            "_worker_name", "my_graph"
        );

        AgentConfig config = normalizer.normalize(raw);

        assertThat(config.getName()).isEqualTo("my_graph");
        assertThat(config.getModel()).isNull();
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
        assertThat(config.getTools()).hasSize(1);
        assertThat(config.getTools().get(0).getName()).isEqualTo("my_graph");
        assertThat(config.getTools().get(0).getToolType()).isEqualTo("worker");
    }

    @Test
    void normalizeUsesDefaultNameWhenMissing() {
        AgentConfig config = normalizer.normalize(Map.of());

        assertThat(config.getName()).isEqualTo("langgraph_agent");
        assertThat(config.getTools().get(0).getName()).isEqualTo("langgraph_agent");
        assertThat(config.getMetadata()).containsEntry("_framework_passthrough", true);
    }
}
