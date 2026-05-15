/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.*;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.conductoross.conductor.ai.models.ChatCompletion;
import org.conductoross.conductor.ai.models.ChatMessage;
import org.conductoross.conductor.ai.models.ToolCall;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

import com.netflix.conductor.common.metadata.workflow.WorkflowTask;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;

/**
 * Tests for AgentChatCompleteTaskMapper.
 */
class AgentChatCompleteTaskMapperTest {

    private final AgentChatCompleteTaskMapper mapper = new AgentChatCompleteTaskMapper();

    @BeforeEach
    void setUp() {
        // @Value("${...}") is not injected outside of Spring; the constructor already sets 5,
        // but be explicit so tests are self-documenting.
        mapper.setRecentExchangesToKeep(5);
    }

    @Test
    void testExtractSubWorkflowResult_extractsResultField() throws Exception {
        Map<String, Object> outputData = new HashMap<>();
        outputData.put("subWorkflowId", "abc-123");
        outputData.put("result", "Afghanistan has a GDP of $20B and a population of 40M.");
        outputData.put("finishReason", "STOP");
        outputData.put("rejectionReason", null);

        Map<String, Object> result = invokeExtractResult(outputData);

        assertThat(result).containsOnlyKeys("result");
        assertThat(result.get("result")).isEqualTo("Afghanistan has a GDP of $20B and a population of 40M.");
    }

    @Test
    void testExtractSubWorkflowResult_nullOutput() throws Exception {
        Map<String, Object> result = invokeExtractResult(null);
        assertThat(result).containsEntry("result", "");
    }

    @Test
    void testExtractSubWorkflowResult_noResultField() throws Exception {
        Map<String, Object> outputData = Map.of("subWorkflowId", "abc-123");
        Map<String, Object> result = invokeExtractResult(outputData);
        // Falls back to full output
        assertThat(result).containsKey("subWorkflowId");
    }

    @Test
    void testExtractSubWorkflowInput_extractsWorkflowInput() throws Exception {
        Map<String, Object> inputData = new HashMap<>();
        inputData.put("subWorkflowDefinition", Map.of("name", "researcher_wf", "tasks", "..."));
        inputData.put("workflowInput", Map.of("prompt", "Afghanistan", "session_id", ""));

        Map<String, Object> result = invokeExtractInput(inputData);

        assertThat(result).containsEntry("prompt", "Afghanistan");
        assertThat(result).containsEntry("session_id", "");
        assertThat(result).doesNotContainKey("subWorkflowDefinition");
    }

    @Test
    void testExtractSubWorkflowInput_nullInput() throws Exception {
        Map<String, Object> result = invokeExtractInput(null);
        assertThat(result).isEmpty();
    }

    @Test
    void testExtractSubWorkflowInput_noWorkflowInput_removesDefinition() throws Exception {
        Map<String, Object> inputData = new HashMap<>();
        inputData.put("subWorkflowDefinition", Map.of("name", "some_wf"));
        inputData.put("otherField", "value");

        Map<String, Object> result = invokeExtractInput(inputData);

        assertThat(result).doesNotContainKey("subWorkflowDefinition");
        assertThat(result).containsEntry("otherField", "value");
    }

    // ── Context condensation tests ─────────────────────────────────

    @Test
    void testCondenseHistory_belowThreshold_noOp() {
        List<ChatMessage> history = new ArrayList<>();
        history.add(new ChatMessage(ChatMessage.Role.assistant, "Hello"));
        history.add(new ChatMessage(ChatMessage.Role.assistant, "World"));

        List<ChatMessage> result = mapper.condenseHistory(history);

        assertThat(result).hasSize(2);
        assertThat(result).isEqualTo(history);
    }

    @Test
    void testCondenseHistory_aboveThreshold_condensed() {
        // Create 12 exchanges (well above RECENT_EXCHANGES_TO_KEEP=5)
        List<ChatMessage> history = new ArrayList<>();
        for (int i = 0; i < 12; i++) {
            history.add(new ChatMessage(ChatMessage.Role.assistant, "Response " + i));
        }

        List<ChatMessage> result = mapper.condenseHistory(history);

        // Should have: 1 summary + 5 recent exchanges
        assertThat(result).hasSize(6);
        // First message is the summary
        assertThat(result.get(0).getRole()).isEqualTo(ChatMessage.Role.assistant);
        assertThat(result.get(0).getMessage()).contains("[Earlier conversation condensed]");
        // Last 5 are the recent messages
        assertThat(result.get(1).getMessage()).isEqualTo("Response 7");
        assertThat(result.get(5).getMessage()).isEqualTo("Response 11");
    }

    @Test
    void testGroupExchanges_toolCallWithResponses() {
        List<ChatMessage> history = new ArrayList<>();

        // tool_call message
        ChatMessage toolCallMsg = new ChatMessage();
        toolCallMsg.setRole(ChatMessage.Role.tool_call);
        toolCallMsg.setToolCalls(List.of(
                ToolCall.builder().name("search").taskReferenceName("ref1").build()));
        history.add(toolCallMsg);

        // tool response
        history.add(new ChatMessage(
                ChatMessage.Role.tool,
                ToolCall.builder()
                        .name("search")
                        .output(Map.of("result", "found"))
                        .build()));

        // assistant text
        history.add(new ChatMessage(ChatMessage.Role.assistant, "Based on the search..."));

        var exchanges = mapper.groupExchanges(history);

        assertThat(exchanges).hasSize(2);
        assertThat(exchanges.get(0).type()).isEqualTo(AgentChatCompleteTaskMapper.ExchangeType.TOOL_EXCHANGE);
        assertThat(exchanges.get(0).messages()).hasSize(2); // tool_call + tool
        assertThat(exchanges.get(1).type()).isEqualTo(AgentChatCompleteTaskMapper.ExchangeType.ASSISTANT_TEXT);
        assertThat(exchanges.get(1).messages()).hasSize(1);
    }

    @Test
    void testGroupExchanges_toolCallResponsePairsNeverSplit() {
        List<ChatMessage> history = new ArrayList<>();

        // tool_call with 3 parallel tool calls
        ChatMessage toolCallMsg = new ChatMessage();
        toolCallMsg.setRole(ChatMessage.Role.tool_call);
        toolCallMsg.setToolCalls(List.of(
                ToolCall.builder().name("tool_a").taskReferenceName("ref1").build(),
                ToolCall.builder().name("tool_b").taskReferenceName("ref2").build(),
                ToolCall.builder().name("tool_c").taskReferenceName("ref3").build()));
        history.add(toolCallMsg);

        // 3 tool responses
        history.add(new ChatMessage(
                ChatMessage.Role.tool,
                ToolCall.builder().name("tool_a").output(Map.of("r", "a")).build()));
        history.add(new ChatMessage(
                ChatMessage.Role.tool,
                ToolCall.builder().name("tool_b").output(Map.of("r", "b")).build()));
        history.add(new ChatMessage(
                ChatMessage.Role.tool,
                ToolCall.builder().name("tool_c").output(Map.of("r", "c")).build()));

        var exchanges = mapper.groupExchanges(history);

        // All 4 messages should be in ONE exchange
        assertThat(exchanges).hasSize(1);
        assertThat(exchanges.get(0).messages()).hasSize(4);
        assertThat(exchanges.get(0).type()).isEqualTo(AgentChatCompleteTaskMapper.ExchangeType.TOOL_EXCHANGE);
    }

    @Test
    void testBuildSummary_format() {
        List<AgentChatCompleteTaskMapper.Exchange> exchanges = new ArrayList<>();

        // A tool exchange
        ChatMessage toolCallMsg = new ChatMessage();
        toolCallMsg.setRole(ChatMessage.Role.tool_call);
        toolCallMsg.setToolCalls(List.of(
                ToolCall.builder().name("run_command").taskReferenceName("ref1").build()));
        ChatMessage toolResp = new ChatMessage(
                ChatMessage.Role.tool,
                ToolCall.builder()
                        .name("run_command")
                        .output(Map.of("status", "success"))
                        .build());
        exchanges.add(new AgentChatCompleteTaskMapper.Exchange(
                List.of(toolCallMsg, toolResp), AgentChatCompleteTaskMapper.ExchangeType.TOOL_EXCHANGE));

        // An assistant text exchange
        exchanges.add(new AgentChatCompleteTaskMapper.Exchange(
                List.of(new ChatMessage(ChatMessage.Role.assistant, "Task completed successfully.")),
                AgentChatCompleteTaskMapper.ExchangeType.ASSISTANT_TEXT));

        String summary = mapper.buildSummary(exchanges);

        assertThat(summary).contains("[Earlier conversation condensed]");
        assertThat(summary).contains("run_command");
        assertThat(summary).contains("Task completed successfully.");
        assertThat(summary).contains("1 tool exchange(s)");
        assertThat(summary).contains("1 assistant response(s)");
    }

    @Test
    void testCondenseHistory_emptyHistory_noOp() {
        List<ChatMessage> result = mapper.condenseHistory(new ArrayList<>());
        assertThat(result).isEmpty();
    }

    @Test
    void testCondenseHistory_fewExchanges_noCondensation() {
        // Only 3 exchanges — below RECENT_EXCHANGES_TO_KEEP (5)
        List<ChatMessage> history = new ArrayList<>();
        history.add(new ChatMessage(ChatMessage.Role.assistant, "One"));
        history.add(new ChatMessage(ChatMessage.Role.assistant, "Two"));
        history.add(new ChatMessage(ChatMessage.Role.assistant, "Three"));

        List<ChatMessage> result = mapper.condenseHistory(history);

        assertThat(result).hasSize(3);
    }

    @Test
    void testTruncate() {
        assertThat(AgentChatCompleteTaskMapper.truncate("short", 10)).isEqualTo("short");
        assertThat(AgentChatCompleteTaskMapper.truncate("a long string here", 6))
                .isEqualTo("a long...");
        assertThat(AgentChatCompleteTaskMapper.truncate(null, 10)).isEqualTo("");
    }

    @Test
    void testSanitizeMessages_dropsBlankTextOnlyMessages() {
        ChatCompletion cc = new ChatCompletion();
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.system, "You are helpful."));
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.user, "   "));

        mapper.sanitizeMessages(cc);

        assertThat(cc.getMessages()).hasSize(1);
        assertThat(cc.getMessages().get(0).getRole()).isEqualTo(ChatMessage.Role.system);
    }

    @Test
    void testSanitizeMessages_keepsMediaOnlyUserMessage() {
        ChatCompletion cc = new ChatCompletion();
        ChatMessage user = new ChatMessage(ChatMessage.Role.user, "   ");
        user.setMedia(List.of("https://example.com/cat.png"));
        cc.getMessages().add(user);

        mapper.sanitizeMessages(cc);

        assertThat(cc.getMessages()).hasSize(1);
        assertThat(cc.getMessages().get(0).getRole()).isEqualTo(ChatMessage.Role.user);
        assertThat(cc.getMessages().get(0).getMessage()).isNull();
        assertThat(cc.getMessages().get(0).getMedia()).containsExactly("https://example.com/cat.png");
    }

    @Test
    void testValidateRunnableConversation_rejectsMissingUserInput() {
        ChatCompletion cc = new ChatCompletion();
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.system, "You are helpful."));

        assertThatThrownBy(() -> mapper.validateRunnableConversation(cc))
                .isInstanceOf(com.netflix.conductor.core.exception.TerminateWorkflowException.class)
                .hasMessageContaining("No non-empty user prompt or media");
    }

    @Test
    void testValidateRunnableConversation_acceptsMediaOnlyUserInput() {
        ChatCompletion cc = new ChatCompletion();
        ChatMessage user = new ChatMessage(ChatMessage.Role.user, "");
        user.setMedia(List.of("https://example.com/cat.png"));
        cc.getMessages().add(user);

        assertThatCode(() -> mapper.validateRunnableConversation(cc)).doesNotThrowAnyException();
    }

    // ── Token limit detection tests ─────────────────────────────────

    @Test
    void testPreviousIterationHitTokenLimit_maxTokens() {
        WorkflowModel workflow = new WorkflowModel();
        List<TaskModel> tasks = new ArrayList<>();

        // Previous iteration completed with MAX_TOKENS
        TaskModel prevTask = new TaskModel();
        prevTask.setStatus(TaskModel.Status.COMPLETED);
        prevTask.setOutputData(Map.of("finishReason", "MAX_TOKENS"));
        WorkflowTask prevWfTask = new WorkflowTask();
        prevWfTask.setTaskReferenceName("llm_call");
        prevTask.setWorkflowTask(prevWfTask);
        tasks.add(prevTask);

        // Current task (being mapped, not yet terminal)
        TaskModel currentTask = new TaskModel();
        currentTask.setStatus(TaskModel.Status.SCHEDULED);
        WorkflowTask currentWfTask = new WorkflowTask();
        currentWfTask.setTaskReferenceName("llm_call");
        currentTask.setWorkflowTask(currentWfTask);
        tasks.add(currentTask);

        workflow.setTasks(tasks);

        assertThat(mapper.previousIterationHitTokenLimit(currentTask, workflow)).isTrue();
    }

    @Test
    void testPreviousIterationHitTokenLimit_length() {
        WorkflowModel workflow = new WorkflowModel();
        List<TaskModel> tasks = new ArrayList<>();

        TaskModel prevTask = new TaskModel();
        prevTask.setStatus(TaskModel.Status.COMPLETED);
        prevTask.setOutputData(Map.of("finishReason", "LENGTH"));
        WorkflowTask prevWfTask = new WorkflowTask();
        prevWfTask.setTaskReferenceName("llm_call");
        prevTask.setWorkflowTask(prevWfTask);
        tasks.add(prevTask);

        TaskModel currentTask = new TaskModel();
        currentTask.setStatus(TaskModel.Status.SCHEDULED);
        WorkflowTask currentWfTask = new WorkflowTask();
        currentWfTask.setTaskReferenceName("llm_call");
        currentTask.setWorkflowTask(currentWfTask);
        tasks.add(currentTask);

        workflow.setTasks(tasks);

        assertThat(mapper.previousIterationHitTokenLimit(currentTask, workflow)).isTrue();
    }

    @Test
    void testPreviousIterationHitTokenLimit_normalStop() {
        WorkflowModel workflow = new WorkflowModel();
        List<TaskModel> tasks = new ArrayList<>();

        TaskModel prevTask = new TaskModel();
        prevTask.setStatus(TaskModel.Status.COMPLETED);
        prevTask.setOutputData(Map.of("finishReason", "STOP"));
        WorkflowTask prevWfTask = new WorkflowTask();
        prevWfTask.setTaskReferenceName("llm_call");
        prevTask.setWorkflowTask(prevWfTask);
        tasks.add(prevTask);

        TaskModel currentTask = new TaskModel();
        currentTask.setStatus(TaskModel.Status.SCHEDULED);
        WorkflowTask currentWfTask = new WorkflowTask();
        currentWfTask.setTaskReferenceName("llm_call");
        currentTask.setWorkflowTask(currentWfTask);
        tasks.add(currentTask);

        workflow.setTasks(tasks);

        assertThat(mapper.previousIterationHitTokenLimit(currentTask, workflow)).isFalse();
    }

    @Test
    void testPreviousIterationHitTokenLimit_firstIteration() {
        WorkflowModel workflow = new WorkflowModel();
        workflow.setTasks(new ArrayList<>());

        TaskModel currentTask = new TaskModel();
        currentTask.setStatus(TaskModel.Status.SCHEDULED);
        WorkflowTask currentWfTask = new WorkflowTask();
        currentWfTask.setTaskReferenceName("llm_call");
        currentTask.setWorkflowTask(currentWfTask);

        assertThat(mapper.previousIterationHitTokenLimit(currentTask, workflow)).isFalse();
    }

    @Test
    void testPreviousIterationHitTokenLimit_checksOnlyMostRecent() {
        WorkflowModel workflow = new WorkflowModel();
        List<TaskModel> tasks = new ArrayList<>();

        // Older iteration hit MAX_TOKENS
        TaskModel oldTask = new TaskModel();
        oldTask.setStatus(TaskModel.Status.COMPLETED);
        oldTask.setOutputData(Map.of("finishReason", "MAX_TOKENS"));
        WorkflowTask oldWfTask = new WorkflowTask();
        oldWfTask.setTaskReferenceName("llm_call");
        oldTask.setWorkflowTask(oldWfTask);
        tasks.add(oldTask);

        // Most recent iteration completed normally
        TaskModel recentTask = new TaskModel();
        recentTask.setStatus(TaskModel.Status.COMPLETED);
        recentTask.setOutputData(Map.of("finishReason", "STOP"));
        WorkflowTask recentWfTask = new WorkflowTask();
        recentWfTask.setTaskReferenceName("llm_call");
        recentTask.setWorkflowTask(recentWfTask);
        tasks.add(recentTask);

        // Current task
        TaskModel currentTask = new TaskModel();
        currentTask.setStatus(TaskModel.Status.SCHEDULED);
        WorkflowTask currentWfTask = new WorkflowTask();
        currentWfTask.setTaskReferenceName("llm_call");
        currentTask.setWorkflowTask(currentWfTask);
        tasks.add(currentTask);

        workflow.setTasks(tasks);

        // Most recent was STOP, not MAX_TOKENS — should be false
        assertThat(mapper.previousIterationHitTokenLimit(currentTask, workflow)).isFalse();
    }

    // ── Token estimation / proactive condensation tests ─────────────

    @Test
    void testEstimateTokenCount_messagesOnly() {
        ChatCompletion cc = new ChatCompletion();
        // 350 chars / 3.5 = 100 tokens
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.assistant, "x".repeat(350)));

        int estimate = mapper.estimateTokenCount(cc);
        assertThat(estimate).isEqualTo(100);
    }

    @Test
    void testEstimateTokenCount_withInstructions() {
        ChatCompletion cc = new ChatCompletion();
        cc.setInstructions("y".repeat(175)); // 175 chars / 3.5 = 50 tokens
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.assistant, "x".repeat(350))); // 100 tokens

        int estimate = mapper.estimateTokenCount(cc);
        assertThat(estimate).isEqualTo(150);
    }

    @Test
    void testEstimateTokenCount_empty() {
        ChatCompletion cc = new ChatCompletion();
        assertThat(mapper.estimateTokenCount(cc)).isEqualTo(0);
    }

    @Test
    void testShouldCondenseProactively_belowThreshold() {
        ChatCompletion cc = new ChatCompletion();
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.assistant, "x".repeat(400))); // ~114 tokens at 3.5 c/t
        // 128K context window, 0 maxTokens, 75% threshold = 96K. 114 tokens << 96K
        assertThat(mapper.shouldCondenseProactively(cc, 128_000, 0)).isFalse();
    }

    @Test
    void testShouldCondenseProactively_aboveThreshold() {
        ChatCompletion cc = new ChatCompletion();
        // 500K chars / 3.5 = ~142K tokens. Input budget = 128K. 142K > 128K → should condense
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.assistant, "x".repeat(500_000)));
        assertThat(mapper.shouldCondenseProactively(cc, 128_000, 0)).isTrue();
    }

    @Test
    void testShouldCondenseProactively_atTriggerFraction() {
        // 75% threshold: 128K * 0.75 = 96K tokens trigger. At 96K tokens
        // (336K chars at 3.5 c/t), still under strict-> → false.
        ChatCompletion cc = new ChatCompletion();
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.assistant, "x".repeat(336_000)));
        assertThat(mapper.shouldCondenseProactively(cc, 128_000, 0)).isFalse();

        // One token over 75% threshold → triggers.
        ChatCompletion cc2 = new ChatCompletion();
        cc2.getMessages().add(new ChatMessage(ChatMessage.Role.assistant, "x".repeat(336_004))); // +4 chars = +1 token
        assertThat(mapper.shouldCondenseProactively(cc2, 128_000, 0)).isTrue();
    }

    @Test
    void testShouldCondenseProactively_safetyMarginCatchesEstimatorUndercount() {
        // Regression for executions cfca8846 / 3d5177a8 where the coder ran
        // gpt-5.3-codex (400K context) and reached OpenAI promptTokens=267,868
        // at iter 17. The next iteration added tool outputs and got rejected
        // with 400 context_length_exceeded because our chars/3.5 estimator
        // undercounted vs OpenAI's real BPE count. Under the old 100% wall
        // (368K input budget), the estimate stayed below threshold even as
        // OpenAI's real count crossed 400K. With a 75% safety fraction, we
        // trigger at 276K estimated, giving real-world headroom.

        // Simulate the iter-17→18 boundary: estimate ~280K tokens (just over
        // the new 276K trigger). At the old 100% threshold (368K) this would
        // NOT have triggered. At 75% it does.
        ChatCompletion cc = new ChatCompletion();
        int chars = (int) (280_000 * 3.5); // ~980K chars → ~280K estimated tokens
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.assistant, "x".repeat(chars)));

        // 400K window, 32K maxTokens reserved (matches the example agent).
        boolean shouldFire = mapper.shouldCondenseProactively(cc, 400_000, 32_000);
        assertThat(shouldFire)
                .as("280K estimated tokens with 400K context / 32K maxTokens must "
                        + "trigger condensation under the 75%% safety threshold "
                        + "(was failing under the old 100%% threshold — see cfca8846)")
                .isTrue();
    }

    @Test
    void testShouldCondenseProactively_accountsForMaxTokens() {
        ChatCompletion cc = new ChatCompletion();
        // 200K chars / 3.5 = ~57K tokens. Input budget = 200K - 60K = 140K.
        // 57K < 140K → should NOT condense
        cc.getMessages().add(new ChatMessage(ChatMessage.Role.assistant, "x".repeat(200_000)));
        assertThat(mapper.shouldCondenseProactively(cc, 200_000, 60_000)).isFalse();

        // 600K chars / 3.5 = ~171K tokens. Input budget = 200K - 60K = 140K.
        // 171K > 140K → should condense
        ChatCompletion cc2 = new ChatCompletion();
        cc2.getMessages().add(new ChatMessage(ChatMessage.Role.assistant, "x".repeat(600_000)));
        assertThat(mapper.shouldCondenseProactively(cc2, 200_000, 60_000)).isTrue();
    }

    // ── Multi-round condensation tests ───────────────────────────────

    /**
     * Verifies that condensation can be applied three times in succession.
     *
     * Simulates the server-side loop:
     *   1. Agent accumulates many exchanges → condensation 1 fires
     *   2. Agent continues, accumulates more → condensation 2 fires
     *   3. Agent continues again → condensation 3 fires
     *
     * Each round: feed condensed output + 10 new messages back into condenseHistory().
     */
    @Test
    void testCondensation_threeCycles() {
        // ── Round 1: 12 exchanges ──────────────────────────────────────────────
        List<ChatMessage> history1 = buildToolExchanges(12);
        List<ChatMessage> after1 = mapper.condenseHistory(history1);

        // 1 summary + 5 recent exchanges (2 msgs each) = 11
        assertThat(after1.get(0).getMessage()).contains("[Earlier conversation condensed]");
        assertThat(after1.get(0).getMessage()).contains("7 tool exchange(s)"); // 12 - 5 condensed
        int sizeAfter1 = after1.size();
        assertThat(sizeAfter1).isLessThan(history1.size());

        // ── Round 2: condensed output + 10 new exchanges ──────────────────────
        List<ChatMessage> history2 = new ArrayList<>(after1);
        history2.addAll(buildToolExchanges(10));
        List<ChatMessage> after2 = mapper.condenseHistory(history2);

        assertThat(after2.get(0).getMessage()).contains("[Earlier conversation condensed]");
        assertThat(after2.size()).isLessThan(history2.size());

        // ── Round 3: condensed output + 10 more new exchanges ─────────────────
        List<ChatMessage> history3 = new ArrayList<>(after2);
        history3.addAll(buildToolExchanges(10));
        List<ChatMessage> after3 = mapper.condenseHistory(history3);

        assertThat(after3.get(0).getMessage()).contains("[Earlier conversation condensed]");
        assertThat(after3.size()).isLessThan(history3.size());
        // Three consecutive condensation cycles must always converge to ≤ keepRecent exchanges + summary
        assertThat(after3.size()).isLessThanOrEqualTo(1 + 5 * 2); // summary + 5 tool exchanges (2 msgs each)
    }

    @Test
    void testCondensation_recentExchangesConfigurable() {
        // Reconfigure to keep only 2 exchanges instead of 5
        mapper.setRecentExchangesToKeep(2);

        List<ChatMessage> history = buildToolExchanges(10); // 10 exchanges
        List<ChatMessage> result = mapper.condenseHistory(history);

        // Should keep: 1 summary + 2 recent exchanges (2 msgs each) = 5
        assertThat(result.get(0).getMessage()).contains("[Earlier conversation condensed]");
        assertThat(result.get(0).getMessage()).contains("8 tool exchange(s)"); // 10 - 2 condensed
        assertThat(result.size()).isEqualTo(5); // 1 summary + 2 * 2
    }

    @Test
    void testCondensation_stillOverBudgetAfterCondensation() {
        // Even after condensing to 5 recent exchanges, a tiny context window
        // may still be over budget. shouldCondenseProactively returns true for both
        // the large and the condensed version — the post-condensation warning path.
        ChatCompletion large = new ChatCompletion();
        large.getMessages().addAll(buildToolExchanges(30)); // very large history

        // Extremely small context window — 200 tokens
        assertThat(mapper.shouldCondenseProactively(large, 200, 0)).isTrue();

        // Even after condensation, the 5 kept exchanges would still exceed 200 tokens
        List<ChatMessage> condensed = mapper.condenseHistory(large.getMessages());
        ChatCompletion afterCondensation = new ChatCompletion();
        afterCondensation.getMessages().addAll(condensed);
        assertThat(mapper.shouldCondenseProactively(afterCondensation, 200, 0)).isTrue();
    }

    // ── Helpers ──────────────────────────────────────────────────────

    @Test
    void testCondenseIfNeeded_pinsUserPromptEvenAfterPrefill() throws Exception {
        // Regression for workflow ``dc9e3c3e``: a no-plan fallback ran 28
        // turns and then failed with "No non-empty user prompt or media".
        // Cause: the prior protection only kept *consecutive* system+user
        // messages from index 0. With prefill_tools the layout is
        //   [system, tool_call, tool, tool_call, tool, user, ...]
        // and ``initialKeep`` stopped at the first tool_call. The user
        // prompt at index 5 fell into the condensable history and was
        // dropped under budget pressure → validateRunnableConversation
        // threw on the next turn. Fix: pin the FIRST user message wherever
        // it sits, in addition to leading system messages.
        ChatCompletion cc = new ChatCompletion();
        // [0] system
        ChatMessage system = new ChatMessage(ChatMessage.Role.system, "You are a coder.");
        cc.getMessages().add(system);
        // [1..4] prefill tool_call/tool pairs (mirrors what compileWithTools
        // emits when prefill_tools is set)
        ChatMessage prefillCall1 = new ChatMessage();
        prefillCall1.setRole(ChatMessage.Role.tool_call);
        prefillCall1.setToolCalls(List.of(ToolCall.builder()
                .name("contextbook_read")
                .taskReferenceName("agent_prefill_0")
                .build()));
        cc.getMessages().add(prefillCall1);
        cc.getMessages()
                .add(new ChatMessage(
                        ChatMessage.Role.tool,
                        ToolCall.builder()
                                .name("contextbook_read")
                                .output(Map.of("result", "issue body…"))
                                .build()));
        ChatMessage prefillCall2 = new ChatMessage();
        prefillCall2.setRole(ChatMessage.Role.tool_call);
        prefillCall2.setToolCalls(List.of(ToolCall.builder()
                .name("contextbook_read")
                .taskReferenceName("agent_prefill_1")
                .build()));
        cc.getMessages().add(prefillCall2);
        cc.getMessages()
                .add(new ChatMessage(
                        ChatMessage.Role.tool,
                        ToolCall.builder()
                                .name("contextbook_read")
                                .output(Map.of("result", "design notes…"))
                                .build()));
        // [5] the actual user prompt — this is what the fix must protect
        ChatMessage user = new ChatMessage(
                ChatMessage.Role.user, "Fix issue #164 from agentspan-ai/agentspan. Working dir: /tmp/wd");
        cc.getMessages().add(user);
        // [6..] a long history that will trigger condensation under tight budget
        cc.getMessages().addAll(buildToolExchanges(40));

        // Tight contextWindowBudget — forces condensation to shrink keepCount.
        TaskModel task = new TaskModel();
        WorkflowTask wfTask = new WorkflowTask();
        wfTask.setTaskReferenceName("agent_llm__29");
        task.setWorkflowTask(wfTask);
        Map<String, Object> input = new HashMap<>();
        input.put("contextWindowBudget", 200); // very tight; forces aggressive shrink
        task.setInputData(input);
        WorkflowModel wf = new WorkflowModel();

        Method m = AgentChatCompleteTaskMapper.class.getDeclaredMethod(
                "condenseIfNeeded", ChatCompletion.class, TaskModel.class, WorkflowModel.class);
        m.setAccessible(true);
        m.invoke(mapper, cc, task, wf);

        // The original user prompt must still be present after condensation —
        // otherwise validateRunnableConversation would throw on the next turn.
        boolean userPreserved = cc.getMessages().stream()
                .anyMatch(msg -> msg.getRole() == ChatMessage.Role.user
                        && msg.getMessage() != null
                        && msg.getMessage().contains("Fix issue #164"));
        assertThat(userPreserved)
                .as("first user prompt must survive condensation regardless of "
                        + "prefill tool_call/tool messages between system and user")
                .isTrue();

        // System message also pinned.
        boolean systemPreserved = cc.getMessages().stream().anyMatch(msg -> msg.getRole() == ChatMessage.Role.system);
        assertThat(systemPreserved).isTrue();
    }

    /**
     * Build {@code n} tool exchanges (tool_call + tool_result message pairs),
     * each with a ~300-char tool output to simulate realistic context growth.
     */
    private List<ChatMessage> buildToolExchanges(int n) {
        List<ChatMessage> messages = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            ChatMessage toolCallMsg = new ChatMessage();
            toolCallMsg.setRole(ChatMessage.Role.tool_call);
            toolCallMsg.setToolCalls(List.of(ToolCall.builder()
                    .name("search")
                    .taskReferenceName("search_" + i)
                    .build()));
            messages.add(toolCallMsg);

            String output = "Search result for query " + i + ": " + "x".repeat(280); // ~300 chars total
            messages.add(new ChatMessage(
                    ChatMessage.Role.tool,
                    ToolCall.builder()
                            .name("search")
                            .output(Map.of("result", output))
                            .build()));
        }
        return messages;
    }

    // Use reflection to test private methods
    @SuppressWarnings("unchecked")
    private Map<String, Object> invokeExtractResult(Map<String, Object> outputData) throws Exception {
        Method method = AgentChatCompleteTaskMapper.class.getDeclaredMethod("extractSubWorkflowResult", Map.class);
        method.setAccessible(true);
        return (Map<String, Object>) method.invoke(mapper, outputData);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> invokeExtractInput(Map<String, Object> inputData) throws Exception {
        Method method = AgentChatCompleteTaskMapper.class.getDeclaredMethod("extractSubWorkflowInput", Map.class);
        method.setAccessible(true);
        return (Map<String, Object>) method.invoke(mapper, inputData);
    }

    // ── compactToolHistory regression tests ─────────────────────────
    //
    // Reproduce two bugs surfaced by workflow 1242e071:
    //   (1) contextbook_read dedup keys by ``inputParameters.section``,
    //       but inputParameters live on the tool_CALL message, not the
    //       tool RESPONSE message. Reading from the response always
    //       returned null, so every read got bucketed as ":toc" and all
    //       but the last were truncated as if duplicates of the same
    //       section.
    //   (2) Prefill tool results were aged out of the recent window
    //       within iteration 1 itself (4 prefills, recent_keep=3 ⇒ the
    //       1st prefill always truncated). Prefills are explicit
    //       user-declared context loads — compaction must not erase them.

    private static String repeatChar(char c, int n) {
        StringBuilder sb = new StringBuilder(n);
        for (int i = 0; i < n; i++) sb.append(c);
        return sb.toString();
    }

    private static ChatMessage toolCallMsg(String toolName, String taskRef, Map<String, Object> args) {
        ChatMessage m = new ChatMessage();
        m.setRole(ChatMessage.Role.tool_call);
        ToolCall.ToolCallBuilder b = ToolCall.builder().name(toolName).taskReferenceName(taskRef);
        if (args != null) b.inputParameters(args);
        m.setToolCalls(List.of(b.build()));
        return m;
    }

    private static ChatMessage toolResponseMsg(String toolName, String taskRef, String result) {
        ChatMessage m = new ChatMessage();
        m.setRole(ChatMessage.Role.tool);
        m.setMessage(result);
        Map<String, Object> outMap = new HashMap<>();
        outMap.put("result", result);
        m.setToolCalls(List.of(ToolCall.builder()
                .name(toolName)
                .taskReferenceName(taskRef)
                .output(outMap)
                .build()));
        return m;
    }

    @Test
    void testCompactToolHistory_distinctContextbookSectionsAllKeptFull() {
        // Three contextbook_read calls of three DIFFERENT sections must all
        // remain full after compaction. Previously the dedup keyed by ":toc"
        // (because inputParameters were absent from the response message),
        // so two of three got truncated as if they were stale duplicates.
        //
        // The taskRefs are intentionally NON-prefill (``toolu_*``) so this
        // test exercises the inputParameters-cross-reference fix in
        // isolation, NOT the prefill-exemption rule.
        String issuePr = "ISSUE_PR_BODY_" + repeatChar('a', 600);
        String design = "DESIGN_BODY_" + repeatChar('b', 600);
        String impl = "IMPL_BODY_" + repeatChar('c', 600);

        List<ChatMessage> messages = new ArrayList<>();
        messages.add(new ChatMessage(ChatMessage.Role.system, "sys"));
        messages.add(toolCallMsg("contextbook_read", "toolu_a__1", Map.of("section", "issue_pr")));
        messages.add(toolResponseMsg("contextbook_read", "toolu_a__1", issuePr));
        messages.add(toolCallMsg("contextbook_read", "toolu_b__2", Map.of("section", "architecture_design_test")));
        messages.add(toolResponseMsg("contextbook_read", "toolu_b__2", design));
        messages.add(toolCallMsg("contextbook_read", "toolu_c__3", Map.of("section", "implementation_report")));
        messages.add(toolResponseMsg("contextbook_read", "toolu_c__3", impl));
        messages.add(new ChatMessage(ChatMessage.Role.user, "review"));

        mapper.compactToolHistory(messages);

        assertThat(messages.get(2).getMessage())
                .as("issue_pr must not be truncated — distinct section, latest read for that section")
                .isEqualTo(issuePr);
        assertThat(messages.get(4).getMessage())
                .as("architecture_design_test must not be truncated — distinct section")
                .isEqualTo(design);
        assertThat(messages.get(6).getMessage())
                .as("implementation_report must not be truncated — distinct section")
                .isEqualTo(impl);
    }

    @Test
    void testCompactToolHistory_prefillResultsNeverTruncated() {
        // Four prefill tool responses + a stretch of regular tool calls.
        // The prefills are at the OLDEST end of the history; under the
        // old rule they would all be truncated by the recent-cutoff. The
        // fix (isPrefillRef) keeps any tool whose taskReferenceName looks
        // like ``<agent>_prefill_<n>`` full, regardless of position.
        String prefill0 = "PREFILL0_" + repeatChar('p', 800);
        String prefill1 = "PREFILL1_" + repeatChar('q', 800);
        String prefill2 = "PREFILL2_" + repeatChar('r', 800);
        String prefill3 = "PREFILL3_" + repeatChar('s', 800);
        String regular0 = "REGULAR0_" + repeatChar('x', 800);
        String regular1 = "REGULAR1_" + repeatChar('y', 800);
        String regular2 = "REGULAR2_" + repeatChar('z', 800);

        List<ChatMessage> messages = new ArrayList<>();
        messages.add(new ChatMessage(ChatMessage.Role.system, "sys"));
        // 4 prefills at the head
        messages.add(toolCallMsg("read_repo_docs", "qa_prefill_0", Map.of()));
        messages.add(toolResponseMsg("read_repo_docs", "qa_prefill_0", prefill0));
        messages.add(toolCallMsg("contextbook_read", "qa_prefill_1", Map.of("section", "issue_pr")));
        messages.add(toolResponseMsg("contextbook_read", "qa_prefill_1", prefill1));
        messages.add(toolCallMsg("contextbook_read", "qa_prefill_2", Map.of("section", "design")));
        messages.add(toolResponseMsg("contextbook_read", "qa_prefill_2", prefill2));
        messages.add(toolCallMsg("contextbook_read", "qa_prefill_3", Map.of("section", "report")));
        messages.add(toolResponseMsg("contextbook_read", "qa_prefill_3", prefill3));
        // 3 regular tool exchanges after — these push the prefills past the
        // recent-cutoff under the old rule.
        messages.add(toolCallMsg("git_diff", "toolu_a__1", Map.of()));
        messages.add(toolResponseMsg("git_diff", "toolu_a__1", regular0));
        messages.add(toolCallMsg("git_diff", "toolu_b__2", Map.of()));
        messages.add(toolResponseMsg("git_diff", "toolu_b__2", regular1));
        messages.add(toolCallMsg("git_diff", "toolu_c__3", Map.of()));
        messages.add(toolResponseMsg("git_diff", "toolu_c__3", regular2));
        messages.add(new ChatMessage(ChatMessage.Role.user, "review"));

        mapper.compactToolHistory(messages);

        // Prefills must remain full
        assertThat(messages.get(2).getMessage())
                .as("read_repo_docs prefill kept full")
                .isEqualTo(prefill0);
        assertThat(messages.get(4).getMessage())
                .as("issue_pr prefill kept full")
                .isEqualTo(prefill1);
        assertThat(messages.get(6).getMessage()).as("design prefill kept full").isEqualTo(prefill2);
        assertThat(messages.get(8).getMessage()).as("report prefill kept full").isEqualTo(prefill3);
    }

    @Test
    void testCompactToolHistory_neverTruncatesToolResults() {
        // Regression for workflow 637d179b: tool results past the
        // "recent N" window USED to be truncated to 200 chars with a
        // ``...[truncated]`` suffix. That made the agent lose context — a
        // 5KB ``glob_find`` result became a 200-char stub, so the agent
        // re-issued nearly-identical queries trying to rediscover the file
        // list. Tool result content is now NEVER truncated; whole-message
        // drop done by condenseIfNeeded handles budget pressure at a
        // cleaner granularity.
        String oldResult = "OLD_REG_" + repeatChar('o', 800);
        String recentResult = "RECENT_REG_" + repeatChar('n', 800);

        List<ChatMessage> messages = new ArrayList<>();
        messages.add(new ChatMessage(ChatMessage.Role.system, "sys"));
        // 5 regular (non-prefill) responses — all must survive intact.
        for (int i = 0; i < 5; i++) {
            String body = (i < 2 ? oldResult : recentResult) + "_iter" + i;
            messages.add(toolCallMsg("git_diff", "toolu_x__" + i, Map.of()));
            messages.add(toolResponseMsg("git_diff", "toolu_x__" + i, body));
        }
        messages.add(new ChatMessage(ChatMessage.Role.user, "go"));

        mapper.compactToolHistory(messages);

        // Every tool response kept full — no truncation suffix anywhere.
        for (int i = 0; i < 5; i++) {
            int msgIdx = 2 + i * 2;
            assertThat(messages.get(msgIdx).getMessage())
                    .as("response %d must not be truncated", i)
                    .doesNotEndWith("...[truncated]")
                    .doesNotEndWith("...");
        }
        // And the underlying toolCalls[0].output.result must also be intact.
        for (int i = 0; i < 5; i++) {
            int msgIdx = 2 + i * 2;
            String body = (i < 2 ? oldResult : recentResult) + "_iter" + i;
            assertThat(messages.get(msgIdx).getMessage()).isEqualTo(body);
            Object outResult =
                    messages.get(msgIdx).getToolCalls().get(0).getOutput().get("result");
            assertThat(outResult).isEqualTo(body);
        }
    }

    @Test
    void testCompactToolHistory_keepsInputParametersOnOldToolCallMessages() {
        // Same failure mode as result truncation, but for ``tool_call``
        // messages: the previous compaction stripped inputParameters from
        // old tool_call messages "to save tokens", which caused the agent
        // to forget what pattern it had searched for and re-issue the same
        // query. Args are now preserved.
        List<ChatMessage> messages = new ArrayList<>();
        messages.add(new ChatMessage(ChatMessage.Role.system, "sys"));
        for (int i = 0; i < 6; i++) {
            messages.add(toolCallMsg(
                    "grep_search", "toolu_p__" + i, Map.of("pattern", "pattern_for_iter_" + i, "path", "src/")));
            messages.add(toolResponseMsg("grep_search", "toolu_p__" + i, "match line " + i));
        }
        messages.add(new ChatMessage(ChatMessage.Role.user, "go"));

        mapper.compactToolHistory(messages);

        // All tool_call messages keep their inputParameters intact.
        for (int i = 0; i < 6; i++) {
            int msgIdx = 1 + i * 2;
            ChatMessage tcMsg = messages.get(msgIdx);
            assertThat(tcMsg.getRole()).isEqualTo(ChatMessage.Role.tool_call);
            Map<String, Object> args = tcMsg.getToolCalls().get(0).getInputParameters();
            assertThat(args)
                    .as("iter %d tool_call inputParameters must survive compaction", i)
                    .containsEntry("pattern", "pattern_for_iter_" + i)
                    .containsEntry("path", "src/");
        }
    }

    // ── Regression: token double-billing on Responses API previousResponseId chains ─
    //
    // When previousResponseId is set on the input, OpenAI's Responses API
    // already has every prior turn of THIS loop in its server-side
    // conversation store. If we ALSO append those same prior turns into the
    // request's messages array, OpenAI counts both — observed in execution
    // 8083490c where iter 14 was billed 259,661 prompt tokens for content
    // that, JSON-serialized, was only ~50K tokens. The phantom ~200K came
    // from doubled state.
    //
    // Conductor's base ChatCompleteTaskMapper.getHistory was already patched
    // to suppress that branch when previousResponseId is in play, but
    // agentspan's AgentChatCompleteTaskMapper overrides getHistory and
    // shadowed the conductor fix — so it has to mirror the same skip.

    @Disabled("previousResponseId auto-threading is currently disabled — see "
            + "AIModelTaskMapper.threadPreviousResponseId javadoc. Re-enable this test "
            + "when the mapper switches to true delta-only message construction.")
    @Test
    void getHistorySuppressesPriorLoopAssistantWhenPreviousResponseIdSet() throws Exception {
        WorkflowModel workflow = new WorkflowModel();
        workflow.setTasks(new ArrayList<>());

        // The task currently being scheduled — same refName as the prior
        // loop iterations (this is the DoWhile shape used by agentspan).
        TaskModel currentTask = makeLoopTask("issue_fixer_coder_llm", null, null);

        // Two prior completed iterations of the same task — these are
        // exactly the "loop assistant" duplicates the Responses API has
        // already absorbed via previousResponseId.
        TaskModel priorIter1 = makeLoopTask("issue_fixer_coder_llm", "First reply.", "resp_one");
        priorIter1.setStatus(TaskModel.Status.COMPLETED);
        priorIter1.setIteration(1);
        workflow.getTasks().add(priorIter1);

        TaskModel priorIter2 = makeLoopTask("issue_fixer_coder_llm", "Second reply.", "resp_two");
        priorIter2.setStatus(TaskModel.Status.COMPLETED);
        priorIter2.setIteration(2);
        workflow.getTasks().add(priorIter2);

        ChatCompletion cc = new ChatCompletion();
        cc.setMessages(new ArrayList<>());
        cc.setPreviousResponseId("resp_two"); // simulate auto-thread on input

        invokeGetHistory(workflow, currentTask, cc);

        // The prior loop assistant messages must NOT have been appended —
        // they live server-side via previousResponseId now.
        boolean sawFirst = cc.getMessages().stream().anyMatch(m -> "First reply.".equals(m.getMessage()));
        boolean sawSecond = cc.getMessages().stream().anyMatch(m -> "Second reply.".equals(m.getMessage()));
        assertThat(sawFirst)
                .as("prior loop assistant message must be suppressed when "
                        + "previousResponseId is set (see execution 8083490c)")
                .isFalse();
        assertThat(sawSecond)
                .as("most-recent prior loop assistant message must be suppressed when " + "previousResponseId is set")
                .isFalse();
    }

    @Test
    void getHistoryStillAppendsPriorLoopAssistantWhenNoPreviousResponseId() throws Exception {
        // Sanity counter-test: without previousResponseId, mode-A stateless
        // semantics apply — the loop history MUST be sent as messages
        // because nothing is on OpenAI's side to recover from.
        WorkflowModel workflow = new WorkflowModel();
        workflow.setTasks(new ArrayList<>());

        TaskModel currentTask = makeLoopTask("issue_fixer_coder_llm", null, null);

        TaskModel priorIter = makeLoopTask("issue_fixer_coder_llm", "Earlier reply.", "resp_one");
        priorIter.setStatus(TaskModel.Status.COMPLETED);
        priorIter.setIteration(1);
        workflow.getTasks().add(priorIter);

        ChatCompletion cc = new ChatCompletion();
        cc.setMessages(new ArrayList<>());
        // Note: no setPreviousResponseId — mode A.

        invokeGetHistory(workflow, currentTask, cc);

        boolean sawEarlier = cc.getMessages().stream().anyMatch(m -> "Earlier reply.".equals(m.getMessage()));
        assertThat(sawEarlier)
                .as("without previousResponseId we are stateless — full loop "
                        + "history MUST be in the messages we send")
                .isTrue();
    }

    @Disabled("previousResponseId auto-threading is currently disabled — see "
            + "AIModelTaskMapper.threadPreviousResponseId javadoc. Re-enable when mode-B "
            + "delta-only message construction is implemented.")
    @Test
    void getHistoryPreservesToolSubtasksEvenWhenPreviousResponseIdSet() throws Exception {
        // Regression for executions e3d54a57 / f3bbdd23: when
        // previousResponseId is set, OpenAI's Responses API still requires
        // the function_call_output items that close out the prior turn's
        // tool_calls. In agentspan's actual workflow shape, tool sub-tasks
        // live as SIBLING tasks (not children) — their refName matches the
        // call_id the LLM emitted. The history rebuild enters the prior LLM
        // task, reads its response.toolCalls, and looks up the matching
        // sibling tool tasks by refName. The original over-aggressive skip
        // dropped the LLM task entry entirely — which meant the tool
        // response lookup never ran, OpenAI saw orphaned prior tool_calls
        // with no matching outputs, and rejected the next call with
        // "No tool output found for function call call_xxx".
        WorkflowModel workflow = new WorkflowModel();
        workflow.setTasks(new ArrayList<>());

        TaskModel currentTask = makeLoopTask("issue_fixer_coder_llm", null, null);

        // Prior LLM iteration that emitted a tool_call. Its outputData
        // carries the toolCalls list — exactly what agentspan reads to
        // discover the sibling tool sub-tasks.
        TaskModel priorLlm = makeLoopTask("issue_fixer_coder_llm", null, "resp_one");
        priorLlm.setStatus(TaskModel.Status.COMPLETED);
        priorLlm.setIteration(1);
        Map<String, Object> priorOut = priorLlm.getOutputData();
        if (priorOut == null) {
            priorOut = new HashMap<>();
            priorLlm.setOutputData(priorOut);
        }
        // The toolCalls list shape mirrors what LLMResponse.toolCalls
        // serializes to. Each entry's taskReferenceName points at the
        // sibling tool sub-task that ran for it.
        priorOut.put(
                "toolCalls",
                List.of(Map.of(
                        "taskReferenceName", "call_ql7zzmWV6y1sKuBceyPh11k1",
                        "name", "read_file",
                        "inputParameters", Map.of("path", "src/Foo.java"),
                        "type", "SIMPLE")));
        priorOut.put("responseId", "resp_one");
        workflow.getTasks().add(priorLlm);

        // Sibling tool sub-task with refName matching the call_id. NO
        // parentTaskReferenceName — that's how the real workflow shape
        // looks (see execution f3bbdd23, tasks 16-20).
        TaskModel toolTask = new TaskModel();
        toolTask.setStatus(TaskModel.Status.COMPLETED);
        toolTask.setTaskType("SIMPLE");
        WorkflowTask twt = new WorkflowTask();
        twt.setName("read_file");
        twt.setTaskReferenceName("call_ql7zzmWV6y1sKuBceyPh11k1");
        twt.setType("SIMPLE");
        toolTask.setWorkflowTask(twt);
        Map<String, Object> toolOut = new HashMap<>();
        toolOut.put("result", "file contents here");
        toolTask.setOutputData(toolOut);
        Map<String, Object> toolIn = new HashMap<>();
        toolIn.put("path", "src/Foo.java");
        toolTask.setInputData(toolIn);
        toolTask.setTaskDefName("read_file");
        workflow.getTasks().add(toolTask);

        ChatCompletion cc = new ChatCompletion();
        cc.setMessages(new ArrayList<>());
        cc.setPreviousResponseId("resp_one");

        invokeGetHistory(workflow, currentTask, cc);

        // The tool RESPONSE message must be in history. agentspan emits a
        // ChatMessage of role=tool whose toolCalls[0].output carries the
        // tool result map. OpenAIResponsesChatModel turns that into a
        // function_call_output InputItem on the wire.
        boolean sawToolOutput = cc.getMessages().stream()
                .filter(m -> m.getRole() == ChatMessage.Role.tool)
                .flatMap(m -> m.getToolCalls() == null
                        ? java.util.stream.Stream.<ToolCall>empty()
                        : m.getToolCalls().stream())
                .anyMatch(tc -> tc.getOutput() != null
                        && "file contents here".equals(tc.getOutput().get("result")));
        assertThat(sawToolOutput)
                .as("tool response message MUST be preserved when previousResponseId "
                        + "is set — OpenAI needs function_call_output to close prior "
                        + "tool_calls (see executions e3d54a57 / f3bbdd23)")
                .isTrue();

        // The assistant tool_call message MUST be suppressed — OpenAI's
        // server-side store already has it via previousResponseId.
        // (Execution 8083490c was the original double-billing observation.)
        boolean sawAssistantToolCallMessage =
                cc.getMessages().stream().anyMatch(m -> m.getRole() == ChatMessage.Role.tool_call);
        assertThat(sawAssistantToolCallMessage)
                .as("prior loop assistant tool_call message MUST be suppressed "
                        + "(it's already on OpenAI's server-side store)")
                .isFalse();
    }

    private static TaskModel makeLoopTask(String refName, String resultText, String responseId) {
        TaskModel t = new TaskModel();
        t.setTaskType("LLM_CHAT_COMPLETE");
        WorkflowTask wt = new WorkflowTask();
        wt.setName("LLM_CHAT_COMPLETE");
        wt.setTaskReferenceName(refName);
        wt.setType("LLM_CHAT_COMPLETE");
        t.setWorkflowTask(wt);
        if (resultText != null) {
            Map<String, Object> out = new HashMap<>();
            out.put("result", resultText);
            if (responseId != null) {
                out.put("responseId", responseId);
            }
            t.setOutputData(out);
        }
        return t;
    }

    private void invokeGetHistory(WorkflowModel wf, TaskModel current, ChatCompletion cc) throws Exception {
        Method method = AgentChatCompleteTaskMapper.class.getDeclaredMethod(
                "getHistory", WorkflowModel.class, TaskModel.class, ChatCompletion.class);
        method.setAccessible(true);
        method.invoke(mapper, wf, current, cc);
    }
}
