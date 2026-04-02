/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.compiler;

import static org.assertj.core.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.Test;

import com.netflix.conductor.common.metadata.workflow.WorkflowTask;

import dev.agentspan.runtime.model.TerminationConfig;

class TerminationCompilerTest {

    @Test
    void testTextMention() {
        TerminationConfig config = TerminationConfig.builder()
                .type("text_mention")
                .text("DONE")
                .caseSensitive(false)
                .build();

        WorkflowTask task = TerminationCompiler.compileTermination(config, "agent", "agent_llm");

        // Termination is now a SIMPLE worker task (Python runtime evaluates the condition)
        assertThat(task.getType()).isEqualTo("SIMPLE");
        assertThat(task.getName()).isEqualTo("agent_termination");
        assertThat(task.getTaskReferenceName()).isEqualTo("agent_termination");
        assertThat(task.getInputParameters()).containsKey("result");
        assertThat(task.getInputParameters()).containsKey("iteration");
    }

    @Test
    void testStopMessage() {
        TerminationConfig config = TerminationConfig.builder()
                .type("stop_message")
                .stopMessage("TERMINATE")
                .build();

        WorkflowTask task = TerminationCompiler.compileTermination(config, "agent", "agent_llm");
        assertThat(task.getType()).isEqualTo("SIMPLE");
        assertThat(task.getName()).isEqualTo("agent_termination");
        // Input binds to LLM output and loop iteration
        assertThat((String) task.getInputParameters().get("result")).contains("agent_llm");
        assertThat((String) task.getInputParameters().get("iteration")).contains("agent_loop");
    }

    @Test
    void testMaxMessage() {
        TerminationConfig config =
                TerminationConfig.builder().type("max_message").maxMessages(10).build();

        WorkflowTask task = TerminationCompiler.compileTermination(config, "agent", "agent_llm");
        assertThat(task.getType()).isEqualTo("SIMPLE");
        assertThat(task.getName()).isEqualTo("agent_termination");
    }

    @Test
    void testAndComposite() {
        TerminationConfig config = TerminationConfig.builder()
                .type("and")
                .conditions(List.of(
                        TerminationConfig.builder()
                                .type("text_mention")
                                .text("DONE")
                                .build(),
                        TerminationConfig.builder()
                                .type("max_message")
                                .maxMessages(5)
                                .build()))
                .build();

        WorkflowTask task = TerminationCompiler.compileTermination(config, "agent", "agent_llm");
        assertThat(task.getType()).isEqualTo("SIMPLE");
        assertThat(task.getName()).isEqualTo("agent_termination");
    }

    @Test
    void testStopWhen() {
        WorkflowTask task = TerminationCompiler.compileStopWhen("my_stop", "agent", "agent_llm");

        assertThat(task.getType()).isEqualTo("SIMPLE");
        assertThat(task.getName()).isEqualTo("my_stop");
        assertThat(task.getTaskReferenceName()).isEqualTo("agent_stop_when");
        // Inputs bind to LLM result, loop iteration, and conversation messages
        assertThat((String) task.getInputParameters().get("result")).contains("agent_llm.output.result");
        assertThat((String) task.getInputParameters().get("iteration")).contains("agent_loop.iteration");
        assertThat((String) task.getInputParameters().get("messages")).contains("agent_llm.input.messages");
    }

    @Test
    void testBuildTerminationScript_textMention() {
        // The script builder is still used for reference/documentation, validate it works
        TerminationConfig config = TerminationConfig.builder()
                .type("text_mention")
                .text("DONE")
                .caseSensitive(false)
                .build();

        String script = TerminationCompiler.buildTerminationScript(config);
        assertThat(script).contains("toLowerCase");
        assertThat(script).contains("DONE");
        assertThat(script).contains("should_continue");
    }

    @Test
    void testBuildTerminationScript_andComposite() {
        TerminationConfig config = TerminationConfig.builder()
                .type("and")
                .conditions(List.of(
                        TerminationConfig.builder()
                                .type("text_mention")
                                .text("DONE")
                                .build(),
                        TerminationConfig.builder()
                                .type("max_message")
                                .maxMessages(5)
                                .build()))
                .build();

        String script = TerminationCompiler.buildTerminationScript(config);
        assertThat(script).contains("should_continue");
        assertThat(script).contains("allTerminate");
    }
}
