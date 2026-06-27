/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.compiler;

import static org.assertj.core.api.Assertions.assertThat;

import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * Regression test: {@link AgentConfig#getMaskedFields()} must be applied to the
 * top-level (user-visible) compiled {@link WorkflowDef} so that field redaction in
 * Conductor execution history / UI actually happens.
 *
 * <p>Deterministic — no LLM, no live server. Verifies the masked fields survive
 * compilation for the single-agent (no tools), tools, and multi-agent shapes.
 */
class MaskedFieldsCompilerTest {

    private static final List<String> MASKED = List.of("ssn", "token");

    @Test
    void singleAgentNoTools_carriesMaskedFields() {
        AgentConfig config = AgentConfig.builder()
                .name("simple_agent")
                .model("openai/gpt-4o")
                .instructions("You are a helpful agent.")
                .maskedFields(MASKED)
                .build();

        WorkflowDef wf = new AgentCompiler().compile(config);

        assertThat(wf.getMaskedFields()).containsExactlyInAnyOrderElementsOf(MASKED);
    }

    @Test
    void toolsPath_carriesMaskedFields() {
        ToolConfig tool = ToolConfig.builder()
                .name("get_weather")
                .description("Get the weather.")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("tools_agent")
                .model("openai/gpt-4o")
                .instructions("You are a helpful agent.")
                .tools(List.of(tool))
                .maskedFields(MASKED)
                .build();

        WorkflowDef wf = new AgentCompiler().compile(config);

        assertThat(wf.getMaskedFields()).containsExactlyInAnyOrderElementsOf(MASKED);
    }

    @Test
    void multiAgent_topLevelCarriesMaskedFields() {
        AgentConfig subAgent = AgentConfig.builder()
                .name("worker_agent")
                .model("openai/gpt-4o")
                .instructions("You are a worker.")
                .build();

        AgentConfig config = AgentConfig.builder()
                .name("coordinator_agent")
                .model("openai/gpt-4o")
                .instructions("You coordinate.")
                .agents(List.of(subAgent))
                .maskedFields(MASKED)
                .build();

        WorkflowDef wf = new AgentCompiler().compile(config);

        // The user-visible top-level workflow must carry maskedFields.
        assertThat(wf.getMaskedFields()).containsExactlyInAnyOrderElementsOf(MASKED);
    }
}
