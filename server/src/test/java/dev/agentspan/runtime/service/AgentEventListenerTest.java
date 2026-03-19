/*
 * Copyright (c) 2025 Agentspan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import dev.agentspan.runtime.model.AgentSSEEvent;

import java.util.Map;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class AgentEventListenerTest {

    private AgentStreamRegistry streamRegistry;
    private AgentEventListener listener;

    @BeforeEach
    void setUp() {
        streamRegistry = mock(AgentStreamRegistry.class);
        listener = new AgentEventListener(streamRegistry);
    }

    private TaskModel makeTask(String workflowId, String taskType, String refName) {
        TaskModel task = new TaskModel();
        task.setWorkflowInstanceId(workflowId);
        task.setTaskType(taskType);
        task.setReferenceTaskName(refName);
        return task;
    }

    private WorkflowModel makeWorkflow(String workflowId) {
        WorkflowModel wf = new WorkflowModel();
        wf.setWorkflowId(workflowId);
        return wf;
    }

    // ── onTaskScheduled ──────────────────────────────────────────────

    @Test
    void onTaskScheduled_llmEmitsThinking() {
        TaskModel task = makeTask("wf-1", "LLM_CHAT_COMPLETE", "agent_llm");

        listener.onTaskScheduled(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("thinking");
        assertThat(captor.getValue().getContent()).isEqualTo("agent_llm");
    }

    @Test
    void onTaskScheduled_subWorkflowEmitsHandoff() {
        TaskModel task = makeTask("wf-1", "SUB_WORKFLOW", "parent_handoff_0_support");
        task.setSubWorkflowId("child-wf-1");

        listener.onTaskScheduled(task);

        // Should register alias
        verify(streamRegistry).registerAlias("child-wf-1", "wf-1");

        // Should emit handoff event
        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("handoff");
        assertThat(captor.getValue().getTarget()).isEqualTo("support");
    }

    @Test
    void onTaskScheduled_subWorkflowNoChildId_noAlias() {
        TaskModel task = makeTask("wf-1", "SUB_WORKFLOW", "parent_handoff_0_agent");
        task.setSubWorkflowId(null);

        listener.onTaskScheduled(task);

        verify(streamRegistry, never()).registerAlias(anyString(), anyString());
        // Should still emit handoff
        verify(streamRegistry).send(eq("wf-1"), any(AgentSSEEvent.class));
    }

    @Test
    void onTaskScheduled_humanNoEvent_handledByAgentHumanTask() {
        // HUMAN tasks are system tasks — Conductor does NOT call onTaskScheduled for them.
        // The WAITING event is emitted by AgentHumanTask.start() instead.
        TaskModel task = makeTask("wf-1", "HUMAN", "hitl_approve");
        task.setInputData(Map.of("tool_name", "publish_article", "parameters", Map.of("title", "Test")));

        listener.onTaskScheduled(task);

        verify(streamRegistry, never()).send(anyString(), any());
    }

    @Test
    void onTaskScheduled_otherTaskType_noEvent() {
        // SWITCH, INLINE, etc. should not emit any event
        TaskModel task = makeTask("wf-1", "SWITCH", "switch_task");

        listener.onTaskScheduled(task);

        verify(streamRegistry, never()).send(anyString(), any());
    }

    // ── onTaskInProgress ─────────────────────────────────────────────

    @Test
    void onTaskInProgress_noEventForAnyType() {
        // Conductor does NOT call onTaskInProgress for system tasks (HUMAN).
        // WAITING is handled by AgentHumanTask.start().
        TaskModel task = makeTask("wf-1", "HUMAN", "hitl_task");
        listener.onTaskInProgress(task);
        verify(streamRegistry, never()).send(anyString(), any());
    }

    @Test
    void onTaskInProgress_nonHuman_noEvent() {
        TaskModel task = makeTask("wf-1", "SIMPLE", "search");

        listener.onTaskInProgress(task);

        verify(streamRegistry, never()).send(anyString(), any());
    }

    // ── onTaskCompleted ──────────────────────────────────────────────

    @Test
    void onTaskCompleted_simpleToolTaskUsesRefAsToolName() {
        TaskModel task = makeTask("wf-1", "SIMPLE", "search_tool");
        task.setInputData(Map.of("query", "hello"));
        task.setOutputData(Map.of("result", "found it"));

        listener.onTaskCompleted(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry, times(2)).send(eq("wf-1"), captor.capture());

        AgentSSEEvent toolCall = captor.getAllValues().get(0);
        assertThat(toolCall.getType()).isEqualTo("tool_call");
        // SIMPLE tasks use reference name as fallback
        assertThat(toolCall.getToolName()).isEqualTo("search_tool");

        AgentSSEEvent toolResult = captor.getAllValues().get(1);
        assertThat(toolResult.getType()).isEqualTo("tool_result");
        assertThat(toolResult.getResult()).isEqualTo("found it");
    }

    @Test
    void onTaskCompleted_serverCompiledToolUsesMethodFromInput() {
        // Server-compiled workflows use SIMPLE tasks where the enrichment
        // script puts the tool name in inputData.method and the call ID
        // as the reference task name.
        TaskModel task = makeTask("wf-1", "SIMPLE", "call_abc123__1");
        task.setInputData(Map.of("method", "get_weather", "city", "NYC"));
        task.setOutputData(Map.of("result", "72F and sunny"));

        listener.onTaskCompleted(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry, times(2)).send(eq("wf-1"), captor.capture());

        AgentSSEEvent toolCall = captor.getAllValues().get(0);
        assertThat(toolCall.getType()).isEqualTo("tool_call");
        // Should use inputData.method (function name), NOT taskRef (call ID)
        assertThat(toolCall.getToolName()).isEqualTo("get_weather");
    }

    @Test
    void onTaskCompleted_simpleDispatchUsesOutputFunction() {
        // Locally-compiled dispatch tasks store function name in output
        TaskModel task = makeTask("wf-1", "SIMPLE", "dispatch_tool");
        task.setInputData(Map.of("q", "test"));
        task.setOutputData(Map.of("function", "calculate", "result", "42"));

        listener.onTaskCompleted(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry, times(2)).send(eq("wf-1"), captor.capture());

        AgentSSEEvent toolCall = captor.getAllValues().get(0);
        assertThat(toolCall.getToolName()).isEqualTo("calculate");
    }

    @Test
    void onTaskCompleted_guardrailPassEmitsGuardrailPass() {
        TaskModel task = makeTask("wf-1", "LLM_CHAT_COMPLETE", "content_guardrail");
        task.setOutputData(Map.of("passed", true));

        listener.onTaskCompleted(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("guardrail_pass");
        assertThat(captor.getValue().getGuardrailName()).isEqualTo("content_guardrail");
    }

    @Test
    void onTaskCompleted_guardrailFailEmitsGuardrailFail() {
        TaskModel task = makeTask("wf-1", "INLINE", "safety_guardrail");
        task.setOutputData(Map.of("passed", false, "message", "Unsafe content"));

        listener.onTaskCompleted(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("guardrail_fail");
        assertThat(captor.getValue().getContent()).isEqualTo("Unsafe content");
    }

    @Test
    void onTaskCompleted_systemTask_noEvent() {
        TaskModel task = makeTask("wf-1", "SWITCH", "route_task");
        task.setOutputData(Map.of("result", "value"));

        listener.onTaskCompleted(task);

        verify(streamRegistry, never()).send(anyString(), any());
    }

    // ── onTaskFailed ─────────────────────────────────────────────────

    @Test
    void onTaskFailed_emitsError() {
        TaskModel task = makeTask("wf-1", "SIMPLE", "search_tool");
        task.setReasonForIncompletion("Connection timeout");

        listener.onTaskFailed(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("error");
        assertThat(captor.getValue().getContent()).isEqualTo("Connection timeout");
    }

    @Test
    void onTaskFailedWithTerminalError_delegatesToOnTaskFailed() {
        TaskModel task = makeTask("wf-1", "SIMPLE", "tool");
        task.setReasonForIncompletion("Fatal error");

        listener.onTaskFailedWithTerminalError(task);

        verify(streamRegistry).send(eq("wf-1"), any(AgentSSEEvent.class));
    }

    @Test
    void onTaskTimedOut_emitsError() {
        TaskModel task = makeTask("wf-1", "SIMPLE", "slow_tool");

        listener.onTaskTimedOut(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("error");
        assertThat(captor.getValue().getContent()).isEqualTo("Task timed out");
    }

    // ── No-op task callbacks ─────────────────────────────────────────

    @Test
    void onTaskCanceled_noEvent() {
        TaskModel task = makeTask("wf-1", "SIMPLE", "tool");
        listener.onTaskCanceled(task);
        verify(streamRegistry, never()).send(anyString(), any());
    }

    @Test
    void onTaskSkipped_noEvent() {
        TaskModel task = makeTask("wf-1", "SIMPLE", "tool");
        listener.onTaskSkipped(task);
        verify(streamRegistry, never()).send(anyString(), any());
    }

    @Test
    void onTaskCompletedWithErrors_delegatesToOnTaskCompleted() {
        TaskModel task = makeTask("wf-1", "SIMPLE", "search_tool");
        task.setInputData(Map.of("q", "test"));
        task.setOutputData(Map.of("result", "partial"));

        listener.onTaskCompletedWithErrors(task);

        // Should emit tool_call + tool_result
        verify(streamRegistry, times(2)).send(eq("wf-1"), any(AgentSSEEvent.class));
    }

    // ── Workflow callbacks ───────────────────────────────────────────

    @Test
    void onWorkflowCompleted_emitsDoneAndCompletes() {
        WorkflowModel wf = makeWorkflow("wf-1");
        wf.setOutput(Map.of("result", "Final answer"));

        listener.onWorkflowCompleted(wf);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("done");
        assertThat(captor.getValue().getOutput()).isEqualTo(Map.of("result", "Final answer"));
        verify(streamRegistry).complete("wf-1");
    }

    @Test
    void onWorkflowCompletedIfEnabled_emitsDoneAndCompletes() {
        WorkflowModel wf = makeWorkflow("wf-1");
        wf.setOutput(Map.of("result", "Answer"));

        listener.onWorkflowCompletedIfEnabled(wf);

        verify(streamRegistry).send(eq("wf-1"), any(AgentSSEEvent.class));
        verify(streamRegistry).complete("wf-1");
    }

    @Test
    void onWorkflowTerminated_emitsErrorAndCompletes() {
        WorkflowModel wf = makeWorkflow("wf-1");
        wf.setReasonForIncompletion("Timeout exceeded");

        listener.onWorkflowTerminated(wf);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("error");
        assertThat(captor.getValue().getContent()).isEqualTo("Timeout exceeded");
        verify(streamRegistry).complete("wf-1");
    }

    @Test
    void onWorkflowTerminated_nullReason_usesDefault() {
        WorkflowModel wf = makeWorkflow("wf-1");
        wf.setReasonForIncompletion(null);

        listener.onWorkflowTerminated(wf);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getContent()).isEqualTo("Workflow terminated");
    }

    @Test
    void onWorkflowTerminatedIfEnabled_emitsErrorAndCompletes() {
        WorkflowModel wf = makeWorkflow("wf-1");
        wf.setReasonForIncompletion("Error");

        listener.onWorkflowTerminatedIfEnabled(wf);

        verify(streamRegistry).send(eq("wf-1"), any(AgentSSEEvent.class));
        verify(streamRegistry).complete("wf-1");
    }

    @Test
    void onWorkflowPausedIfEnabled_emitsWaiting() {
        WorkflowModel wf = makeWorkflow("wf-1");

        listener.onWorkflowPausedIfEnabled(wf);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("waiting");
        assertThat(captor.getValue().getPendingTool()).isEmpty();
    }

    // ── No-op workflow callbacks ─────────────────────────────────────

    @Test
    void onWorkflowStartedIfEnabled_noEvent() {
        WorkflowModel wf = makeWorkflow("wf-1");
        listener.onWorkflowStartedIfEnabled(wf);
        verify(streamRegistry, never()).send(anyString(), any());
    }

    @Test
    void onWorkflowResumedIfEnabled_noEvent() {
        WorkflowModel wf = makeWorkflow("wf-1");
        listener.onWorkflowResumedIfEnabled(wf);
        verify(streamRegistry, never()).send(anyString(), any());
    }

    @Test
    void onWorkflowFinalizedIfEnabled_noEvent() {
        WorkflowModel wf = makeWorkflow("wf-1");
        listener.onWorkflowFinalizedIfEnabled(wf);
        verify(streamRegistry, never()).send(anyString(), any());
    }

    // ── Error handling ───────────────────────────────────────────────

    @Test
    void emitSwallowsExceptions() {
        doThrow(new RuntimeException("send failed"))
                .when(streamRegistry).send(anyString(), any());

        TaskModel task = makeTask("wf-1", "LLM_CHAT_COMPLETE", "llm");

        // Should not throw
        assertThatCode(() -> listener.onTaskScheduled(task)).doesNotThrowAnyException();
    }

    // ── extractHandoffTarget ─────────────────────────────────────────

    @Test
    void onTaskScheduled_handoffStrategy_extractsAgentName() {
        // Handoff/Router: {parent}_handoff_{idx}_{child}
        TaskModel task = makeTask("wf-1", "SUB_WORKFLOW", "support_handoff_0_billing");
        task.setSubWorkflowId("child-1");

        listener.onTaskScheduled(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getType()).isEqualTo("handoff");
        assertThat(captor.getValue().getTarget()).isEqualTo("billing");
    }

    @Test
    void onTaskScheduled_sequentialStrategy_extractsAgentName() {
        // Sequential: {parent}_step_{idx}_{child}
        TaskModel task = makeTask("wf-1", "SUB_WORKFLOW", "pipeline_step_0_researcher");
        task.setSubWorkflowId("child-2");

        listener.onTaskScheduled(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getTarget()).isEqualTo("researcher");
    }

    @Test
    void onTaskScheduled_parallelStrategy_extractsAgentName() {
        // Parallel: {parent}_parallel_{idx}_{child}
        TaskModel task = makeTask("wf-1", "SUB_WORKFLOW", "analysis_parallel_0_pros_analyst");
        task.setSubWorkflowId("child-3");

        listener.onTaskScheduled(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getTarget()).isEqualTo("pros_analyst");
    }

    @Test
    void onTaskScheduled_roundRobinStrategy_extractsAgentName() {
        // Round-robin: {parent}_agent_{idx}_{child}
        TaskModel task = makeTask("wf-1", "SUB_WORKFLOW", "debate_agent_1_pessimist__1");
        task.setSubWorkflowId("child-4");

        listener.onTaskScheduled(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getTarget()).isEqualTo("pessimist");
    }

    @Test
    void onTaskScheduled_indexedPrefix_extractsAgentName() {
        // Fallback: {idx}_{child}
        TaskModel task = makeTask("wf-1", "SUB_WORKFLOW", "0_billing__1");
        task.setSubWorkflowId("child-5");

        listener.onTaskScheduled(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getTarget()).isEqualTo("billing");
    }

    @Test
    void onTaskScheduled_simpleRefNameAsTarget() {
        // Clean name: no prefix to strip
        TaskModel task = makeTask("wf-1", "SUB_WORKFLOW", "assistant");
        task.setSubWorkflowId("child-6");

        listener.onTaskScheduled(task);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        assertThat(captor.getValue().getTarget()).isEqualTo("assistant");
    }

    @Test
    void onTaskCompleted_fwPrefixedTaskDoesNotEmitToolEvent() {
        TaskModel task = makeTask("wf-fw", "SIMPLE", "_fw_task");

        listener.onTaskCompleted(task);

        // No tool_call or tool_result events should be sent for _fw_ tasks
        verify(streamRegistry, never()).send(any(), any());
    }

    @Test
    void onTaskCompleted_regularSimpleTaskEmitsToolResult() {
        TaskModel task = makeTask("wf-tool", "SIMPLE", "search_tool");

        listener.onTaskCompleted(task);

        // A regular SIMPLE task SHOULD emit both tool_call and tool_result events
        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry, times(2)).send(eq("wf-tool"), captor.capture());
        assertThat(captor.getAllValues().get(1).getType()).isEqualTo("tool_result");
    }
}
