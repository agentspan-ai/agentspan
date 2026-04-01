/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.ai;

import static com.netflix.conductor.common.metadata.tasks.TaskType.TASK_TYPE_HTTP;
import static com.netflix.conductor.common.metadata.tasks.TaskType.TASK_TYPE_SIMPLE;
import static com.netflix.conductor.common.metadata.tasks.TaskType.TASK_TYPE_SUB_WORKFLOW;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalInt;
import java.util.Set;

import org.conductoross.conductor.ai.models.ChatCompletion;
import org.conductoross.conductor.ai.models.ChatMessage;
import org.conductoross.conductor.ai.models.LLMResponse;
import org.conductoross.conductor.ai.models.Media;
import org.conductoross.conductor.ai.models.ToolCall;
import org.conductoross.conductor.ai.tasks.mapper.AIModelTaskMapper;
import org.conductoross.conductor.common.utils.StringTemplate;
import org.conductoross.conductor.config.AIIntegrationEnabledCondition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Primary;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import com.netflix.conductor.core.exception.TerminateWorkflowException;
import com.netflix.conductor.core.execution.mapper.TaskMapperContext;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;

import dev.agentspan.runtime.model.AgentSSEEvent;
import dev.agentspan.runtime.service.AgentStreamRegistry;
import dev.agentspan.runtime.util.ModelContextWindows;

/**
 * Custom override of Conductor's ChatCompleteTaskMapper that properly
 * handles SUB_WORKFLOW task results in the conversation history.
 *
 * <p>The upstream mapper puts raw SUB_WORKFLOW metadata (subWorkflowDefinition,
 * workflowInput, etc.) into tool messages instead of extracting the actual
 * result. This causes the coordinator LLM to see garbage tool results,
 * especially in scatter-gather patterns with many parallel sub-agents.</p>
 *
 * <p>This mapper fixes the SUB_WORKFLOW handling to:</p>
 * <ul>
 *   <li>Extract clean input from the original tool call arguments</li>
 *   <li>Extract just the {@code result} field from SUB_WORKFLOW output</li>
 *   <li>Avoid duplicate tool_call/tool entries from direct SUB_WORKFLOW
 *       iteration since the LLM toolCalls path already covers them</li>
 * </ul>
 */
@Component
@Primary
@Order(Ordered.HIGHEST_PRECEDENCE)
@Conditional(AIIntegrationEnabledCondition.class)
public class AgentChatCompleteTaskMapper extends AIModelTaskMapper<ChatCompletion> {

    @SuppressWarnings("HidingField")
    private static final Logger log = LoggerFactory.getLogger(AgentChatCompleteTaskMapper.class);

    private static final Set<String> TOOL_TASK_TYPES = Set.of(TASK_TYPE_HTTP, TASK_TYPE_SIMPLE, "MCP", "CALL_MCP_TOOL");

    private static final int SUMMARY_TEXT_LIMIT = 200;
    private static final int TOOL_OUTPUT_SUMMARY_LIMIT = 150;
    private static final double CHARS_PER_TOKEN = 3.5;

    enum ExchangeType {
        TOOL_EXCHANGE,
        ASSISTANT_TEXT,
        USER_MESSAGE,
        OTHER
    }

    record Exchange(List<ChatMessage> messages, ExchangeType type) {}

    @Value("${agentspan.context-condensation.recent-exchanges:5}")
    private int recentExchangesToKeep;

    @Autowired(required = false)
    private ModelContextWindows modelContextWindows;

    @Autowired(required = false)
    private AgentStreamRegistry streamRegistry;

    public AgentChatCompleteTaskMapper() {
        super(ChatCompletion.NAME);
        this.recentExchangesToKeep = 5; // default; overridden by @Value in Spring context
    }

    /** Package-private for testing — {@code @Value} is not injected outside of Spring. */
    void setRecentExchangesToKeep(int n) {
        this.recentExchangesToKeep = n;
    }

    @Override
    protected TaskModel getMappedTask(TaskMapperContext taskMapperContext) throws TerminateWorkflowException {
        // Call AIModelTaskMapper.getMappedTask() to create the base TaskModel
        // (skips ChatCompleteTaskMapper's broken getHistory)
        TaskModel taskModel = super.getMappedTask(taskMapperContext);
        WorkflowModel workflowModel = taskMapperContext.getWorkflowModel();

        // Per-user LLM key resolution is handled by AgentspanAIModelProvider.getModel()
        // which creates a fresh AIModel with the user's credential. No inputData injection needed.

        try {
            ChatCompletion chatCompletion = objectMapper.convertValue(taskModel.getInputData(), ChatCompletion.class);
            List<ChatMessage> history = chatCompletion.getMessages();
            if (chatCompletion.getUserInput() != null
                    && chatCompletion.getMessages().isEmpty()) {
                history.add(new ChatMessage(ChatMessage.Role.user, chatCompletion.getUserInput()));
            }
            getHistory(workflowModel, taskModel, chatCompletion);
            condenseIfNeeded(chatCompletion, taskModel, workflowModel);
            ensureEndsWithUserMessage(chatCompletion, taskModel);
            updateTaskModel(chatCompletion, taskModel);
        } catch (Exception e) {
            if (e instanceof TerminateWorkflowException) {
                throw (TerminateWorkflowException) e;
            } else {
                log.error("input: {}", taskModel.getInputData());
                log.error(e.getMessage(), e);
                throw new TerminateWorkflowException(
                        String.format("Error preparing chat completion task input: %s", e.getMessage()));
            }
        }
        return taskModel;
    }

    private void updateTaskModel(ChatCompletion chatCompletion, TaskModel simpleTask) {
        Map<String, Object> paramReplacement = chatCompletion.getPromptVariables();
        if (paramReplacement == null) {
            paramReplacement = new HashMap<>();
        }
        List<ChatMessage> messages = chatCompletion.getMessages();
        if (messages == null) {
            messages = new ArrayList<>();
        }
        for (ChatMessage message : messages) {
            String msgText = message.getMessage();
            if (msgText != null) {
                msgText = StringTemplate.fString(msgText, paramReplacement);
                message.setMessage(msgText);
            }
        }
        simpleTask.getInputData().put("messages", messages);
        simpleTask.getInputData().put("tools", chatCompletion.getTools());
    }

    /**
     * Build conversation history from completed tasks in the workflow.
     *
     * <p>This is a fixed version of the upstream ChatCompleteTaskMapper's
     * private getHistory method. The key changes:</p>
     * <ul>
     *   <li>SUB_WORKFLOW tasks encountered directly are skipped (they're
     *       handled via the LLM toolCalls path to avoid duplicates)</li>
     *   <li>When resolving tool results for SUB_WORKFLOW tasks via toolCalls,
     *       the result is extracted cleanly from outputData.result instead of
     *       sending raw metadata</li>
     * </ul>
     */
    private void getHistory(WorkflowModel workflow, TaskModel chatCompleteTask, ChatCompletion chatCompletion) {

        Map<String, List<TaskModel>> refNameToTask = new HashMap<>();
        for (TaskModel task : workflow.getTasks()) {
            refNameToTask
                    .computeIfAbsent(task.getWorkflowTask().getTaskReferenceName(), k -> new ArrayList<>())
                    .add(task);
        }

        String historyContextTaskRefName = chatCompleteTask.getWorkflowTask().getTaskReferenceName();
        if (chatCompleteTask.getParentTaskReferenceName() != null) {
            historyContextTaskRefName = chatCompleteTask.getParentTaskReferenceName();
        }

        List<ChatMessage> history = new ArrayList<>();

        for (TaskModel task : workflow.getTasks()) {
            if (!task.getStatus().isTerminal()) {
                continue;
            }

            boolean skipTask = true;
            ChatMessage.Role role = ChatMessage.Role.assistant;

            if (task.getParentTaskReferenceName() != null
                    && task.getParentTaskReferenceName().equals(historyContextTaskRefName)) {
                skipTask = false;
            } else if (task.isLoopOverTask()
                    && task.getWorkflowTask().getTaskReferenceName().equals(historyContextTaskRefName)) {
                skipTask = false;
            } else if (chatCompletion.getParticipants() != null) {
                ChatMessage.Role participantRole = chatCompletion
                        .getParticipants()
                        .get(task.getWorkflowTask().getTaskReferenceName());
                if (participantRole != null) {
                    role = participantRole;
                    skipTask = false;
                }
            }

            if (skipTask) {
                continue;
            }

            log.trace("\nTask {} - {} will be used for history", task.getReferenceTaskName(), task.getTaskType());

            LLMResponse response = null;
            try {
                response = objectMapper.convertValue(task.getOutputData(), LLMResponse.class);
            } catch (Exception ignore) {
                response = LLMResponse.builder().result(task.getOutputData()).build();
            }

            if (TOOL_TASK_TYPES.contains(task.getWorkflowTask().getType())) {
                // SIMPLE/HTTP/MCP tool — keep original behavior
                ToolCall toolCall = ToolCall.builder()
                        .inputParameters(task.getInputData())
                        .name(task.getTaskDefName())
                        .taskReferenceName(task.getReferenceTaskName())
                        .type(task.getTaskType())
                        .output(task.getOutputData())
                        .build();
                history.add(new ChatMessage(ChatMessage.Role.tool, toolCall));

            } else if (TASK_TYPE_SUB_WORKFLOW.equals(task.getWorkflowTask().getType())) {
                // SUB_WORKFLOW — skip direct entries. These are handled via
                // the LLM toolCalls path below, which has the original tool call
                // context and avoids sending raw sub-workflow metadata.
                log.trace(
                        "Skipping direct SUB_WORKFLOW entry for {} — handled via toolCalls path",
                        task.getReferenceTaskName());

            } else if (response.getToolCalls() != null
                    && !response.getToolCalls().isEmpty()) {
                // LLM task with toolCalls — look up executed tasks and build
                // ONE assistant message with ALL tool calls, then individual
                // tool response messages. This matches the OpenAI API format
                // where one assistant message contains all parallel tool calls.
                List<ToolCall> assistantToolCalls = new ArrayList<>();
                List<ChatMessage> toolResponses = new ArrayList<>();

                for (ToolCall toolCall : response.getToolCalls()) {
                    String toolRefName = toolCall.getTaskReferenceName();
                    List<TaskModel> toolModels = refNameToTask.getOrDefault(toolRefName, new ArrayList<>());
                    for (TaskModel toolModel : toolModels) {
                        if (!toolModel.getStatus().isTerminal()) continue;

                        // Append retry count to ensure unique tool_use ids across retries
                        String uniqueRefName = toolModel.getWorkflowTask().getTaskReferenceName();
                        if (toolModel.getRetryCount() > 0) {
                            uniqueRefName = uniqueRefName + "_retry" + toolModel.getRetryCount();
                        }

                        // Build a tool call with the unique ref name for the assistant message
                        ToolCall uniqueToolCall = ToolCall.builder()
                                .inputParameters(toolCall.getInputParameters())
                                .name(toolCall.getName())
                                .taskReferenceName(uniqueRefName)
                                .type(toolCall.getType())
                                .build();
                        assistantToolCalls.add(uniqueToolCall);

                        if (toolModel.getStatus().isSuccessful()) {
                            // For SUB_WORKFLOW tasks, extract clean result
                            Map<String, Object> toolOutput = toolModel.getOutputData();
                            Map<String, Object> toolInput = toolModel.getInputData();

                            if (TASK_TYPE_SUB_WORKFLOW.equals(toolModel.getTaskType())) {
                                toolOutput = extractSubWorkflowResult(toolOutput);
                                toolInput = extractSubWorkflowInput(toolInput);
                            }

                            ToolCall toolCallResult = ToolCall.builder()
                                    .inputParameters(toolInput)
                                    .name(toolModel.getTaskDefName())
                                    .taskReferenceName(uniqueRefName)
                                    .type(toolModel.getTaskType())
                                    .output(toolOutput)
                                    .build();
                            toolResponses.add(new ChatMessage(ChatMessage.Role.tool, toolCallResult));
                        } else {
                            // Failed tool — send error feedback to LLM
                            String reason = toolModel.getReasonForIncompletion();
                            if (reason == null || reason.isEmpty()) {
                                reason = "Tool execution failed (status: " + toolModel.getStatus() + ")";
                            }
                            Map<String, Object> errorOutput = Map.of("status", "FAILED", "error", reason);
                            ToolCall toolCallResult = ToolCall.builder()
                                    .inputParameters(toolModel.getInputData())
                                    .name(toolModel.getTaskDefName())
                                    .taskReferenceName(uniqueRefName)
                                    .type(toolModel.getTaskType())
                                    .output(errorOutput)
                                    .build();
                            toolResponses.add(new ChatMessage(ChatMessage.Role.tool, toolCallResult));
                        }
                    }
                }

                // Emit ONE assistant message with all tool calls, then all responses
                if (!assistantToolCalls.isEmpty()) {
                    ChatMessage assistantMsg = new ChatMessage();
                    assistantMsg.setRole(ChatMessage.Role.tool_call);
                    assistantMsg.setToolCalls(assistantToolCalls);
                    history.add(assistantMsg);
                    history.addAll(toolResponses);
                }

            } else {
                // Other tasks — assistant messages, etc.
                if (response.getResult() != null) {
                    Object resultObj = response.getResult();
                    if (resultObj instanceof Map<?, ?>) {
                        if (((Map<?, ?>) resultObj).containsKey("response")) {
                            resultObj = ((Map<?, ?>) resultObj).get("response");
                        }
                    }
                    String text = String.valueOf(resultObj);

                    // When a prior LLM turn hit MAX_TOKENS, its partial text would
                    // become an assistant message. Claude rejects conversations ending
                    // with assistant messages ("assistant message prefill"). Convert
                    // the partial assistant text to a user continuation message instead.
                    String finishReason = response.getFinishReason();
                    boolean hitTokenLimit = "MAX_TOKENS".equals(finishReason) || "LENGTH".equals(finishReason);
                    ChatMessage.Role msgRole = hitTokenLimit ? ChatMessage.Role.user : role;
                    String msgText = hitTokenLimit && text != null && !text.isBlank()
                            ? "You were saying:\n\n" + text + "\n\nPlease continue where you left off."
                            : text;

                    var msg = new ChatMessage(msgRole, msgText);
                    if (response.getMedia() != null) {
                        msg.setMedia(response.getMedia().stream()
                                .map(Media::getLocation)
                                .toList());
                    }
                    history.add(msg);
                }
            }
        }
        chatCompletion.getMessages().addAll(history);
    }

    // ── Context condensation ─────────────────────────────────────────

    /**
     * Condense conversation history proactively (approaching context window) or
     * reactively (previous iteration hit the token limit).
     */
    private void condenseIfNeeded(ChatCompletion chatCompletion, TaskModel task, WorkflowModel workflow) {
        boolean reactive = previousIterationHitTokenLimit(task, workflow);

        // Always resolve context window so we can warn after condensation even on reactive triggers
        int contextWindow = 0;
        int maxTokens = 0;
        if (modelContextWindows != null) {
            String model = (String) task.getInputData().get("model");
            OptionalInt contextWindowOpt = modelContextWindows.getContextWindow(model);
            if (contextWindowOpt.isPresent()) {
                contextWindow = contextWindowOpt.getAsInt();
                Object maxTokensObj = task.getInputData().get("maxTokens");
                maxTokens = maxTokensObj instanceof Number ? ((Number) maxTokensObj).intValue() : 0;
            }
        }

        boolean proactive =
                !reactive && contextWindow > 0 && shouldCondenseProactively(chatCompletion, contextWindow, maxTokens);

        if (!reactive && !proactive) {
            return;
        }

        List<ChatMessage> messages = chatCompletion.getMessages();

        // Find how many initial messages to always keep (system + first user)
        int initialKeep = 0;
        for (int i = 0; i < messages.size(); i++) {
            ChatMessage.Role role = messages.get(i).getRole();
            if (role == ChatMessage.Role.system || (role == ChatMessage.Role.user && initialKeep == i)) {
                initialKeep = i + 1;
            } else {
                break;
            }
        }

        // Split: initial messages (keep) + history (condense)
        List<ChatMessage> initial = new ArrayList<>(messages.subList(0, initialKeep));
        List<ChatMessage> history = new ArrayList<>(messages.subList(initialKeep, messages.size()));

        if (history.isEmpty()) {
            return;
        }

        int messagesBefore = initial.size() + history.size();
        int totalExchanges = groupExchanges(history).size();
        int keptExchanges = Math.min(recentExchangesToKeep, totalExchanges);
        int exchangesCondensed = totalExchanges - keptExchanges;

        List<ChatMessage> condensed = condenseHistory(history);

        messages.clear();
        messages.addAll(initial);
        messages.addAll(condensed);

        String trigger = reactive ? "token limit hit" : "proactive (exceeds context window)";
        int messagesAfter = messages.size();
        log.info(
                "Condensed conversation from {} to {} messages (triggered by {})",
                messagesBefore,
                messagesAfter,
                trigger);

        // Store condensation metadata on the task for audit trail and UI visibility
        task.getInputData()
                .put(
                        "_condensation",
                        Map.of(
                                "trigger", trigger,
                                "messagesBefore", messagesBefore,
                                "messagesAfter", messagesAfter,
                                "exchangesCondensed", exchangesCondensed));

        // Emit SSE event so connected clients know condensation occurred
        if (streamRegistry != null) {
            streamRegistry.send(
                    workflow.getWorkflowId(),
                    AgentSSEEvent.contextCondensed(
                            workflow.getWorkflowId(), trigger, messagesBefore, messagesAfter, exchangesCondensed));
        }

        // Warn if still over budget after condensation — nothing more we can do at this point
        if (contextWindow > 0) {
            int inputBudget = contextWindow - Math.max(maxTokens, 0);
            int afterTokens = estimateTokenCount(chatCompletion);
            if (afterTokens > inputBudget) {
                log.warn(
                        "Context still exceeds budget after condensation: ~{} tokens estimated vs {} input budget "
                                + "(contextWindow={}, maxTokens={}). Model may truncate or reject the request.",
                        afterTokens,
                        inputBudget,
                        contextWindow,
                        maxTokens);
            }
        }
    }

    /**
     * Check if the estimated token count exceeds the proactive condensation threshold.
     * The available input budget is {@code contextWindow - maxTokens} (the API rejects
     * requests where {@code inputTokens + maxTokens > contextWindow}).
     */
    boolean shouldCondenseProactively(ChatCompletion chatCompletion, int contextWindow, int maxTokens) {
        int estimatedTokens = estimateTokenCount(chatCompletion);
        int inputBudget = contextWindow - Math.max(maxTokens, 0);
        if (estimatedTokens > inputBudget) {
            log.info(
                    "Proactive condensation: estimated {} tokens exceeds {} input budget (contextWindow={}, maxTokens={})",
                    estimatedTokens,
                    inputBudget,
                    contextWindow,
                    maxTokens);
            return true;
        }
        return false;
    }

    /**
     * Estimate token count using a rough heuristic of ~4 characters per token.
     * Accounts for message content, tool calls, tool definitions, and instructions.
     */
    int estimateTokenCount(ChatCompletion chatCompletion) {
        long totalChars = 0;

        // Message content
        for (ChatMessage msg : chatCompletion.getMessages()) {
            if (msg.getMessage() != null) {
                totalChars += msg.getMessage().length();
            }
            if (msg.getToolCalls() != null) {
                for (ToolCall tc : msg.getToolCalls()) {
                    if (tc.getName() != null) totalChars += tc.getName().length();
                    if (tc.getInputParameters() != null) {
                        totalChars += tc.getInputParameters().toString().length();
                    }
                    if (tc.getOutput() != null) {
                        totalChars += tc.getOutput().toString().length();
                    }
                }
            }
        }

        // Tool definitions — JSON-serialize for accurate size (toString() gives Java repr, not JSON)
        if (chatCompletion.getTools() != null) {
            try {
                totalChars += objectMapper
                        .writeValueAsString(chatCompletion.getTools())
                        .length();
            } catch (Exception e) {
                totalChars += chatCompletion.getTools().toString().length();
            }
        }

        // Instructions / system prompt
        if (chatCompletion.getInstructions() != null) {
            totalChars += chatCompletion.getInstructions().length();
        }

        return (int) (totalChars / CHARS_PER_TOKEN);
    }

    /**
     * Ensure the conversation ends with a user message. Claude/Anthropic models reject
     * conversations ending with an assistant message ("assistant message prefill").
     * This happens after a MAX_TOKENS finish where the partial assistant text is appended.
     * Adds a "Please continue." user message if needed.
     */
    private void ensureEndsWithUserMessage(ChatCompletion chatCompletion, TaskModel task) {
        List<ChatMessage> messages = chatCompletion.getMessages();
        if (messages == null || messages.isEmpty()) return;

        ChatMessage last = messages.get(messages.size() - 1);
        ChatMessage.Role lastRole = last.getRole();
        String roleStr = lastRole != null ? String.valueOf(lastRole) : "null";

        // Claude models reject conversations not ending with a user or tool message.
        boolean needsContinuation = !"user".equalsIgnoreCase(roleStr) && !"tool".equalsIgnoreCase(roleStr);

        if (needsContinuation) {
            log.info(
                    "Appending user continuation message (last role was '{}', total messages: {})",
                    roleStr,
                    messages.size());
            messages.add(new ChatMessage(ChatMessage.Role.user, "Please continue where you left off."));
        }
    }

    /**
     * Check if the previous iteration of this task hit the token limit.
     * Scans completed tasks in the workflow with the same reference name
     * (i.e. previous loop iterations) and checks the most recent one's finishReason.
     */
    boolean previousIterationHitTokenLimit(TaskModel currentTask, WorkflowModel workflow) {
        String currentRef = currentTask.getWorkflowTask().getTaskReferenceName();

        TaskModel previousIteration = null;
        for (TaskModel task : workflow.getTasks()) {
            if (task == currentTask) continue;
            if (!task.getStatus().isTerminal()) continue;
            if (currentRef.equals(task.getWorkflowTask().getTaskReferenceName())) {
                previousIteration = task; // last match = most recent iteration
            }
        }

        if (previousIteration == null) return false;

        Object finishReason = previousIteration.getOutputData().get("finishReason");
        return "LENGTH".equals(finishReason) || "MAX_TOKENS".equals(finishReason);
    }

    /**
     * Condense a history message list by summarizing older exchanges
     * and keeping the most recent ones verbatim.
     */
    List<ChatMessage> condenseHistory(List<ChatMessage> history) {
        List<Exchange> exchanges = groupExchanges(history);

        int keepCount = Math.min(recentExchangesToKeep, exchanges.size());
        int condenseBoundary = exchanges.size() - keepCount;

        if (condenseBoundary <= 0) {
            return history; // too few exchanges to condense
        }

        List<Exchange> olderExchanges = exchanges.subList(0, condenseBoundary);
        List<Exchange> recentExchanges = exchanges.subList(condenseBoundary, exchanges.size());

        String summaryText = buildSummary(olderExchanges);

        List<ChatMessage> condensed = new ArrayList<>();
        condensed.add(new ChatMessage(ChatMessage.Role.assistant, summaryText));
        for (Exchange ex : recentExchanges) {
            condensed.addAll(ex.messages());
        }

        return condensed;
    }

    /**
     * Group a flat list of ChatMessages into logical exchanges.
     * A tool_call + its subsequent tool responses form one exchange.
     * An assistant text message is one exchange. Etc.
     */
    List<Exchange> groupExchanges(List<ChatMessage> history) {
        List<Exchange> exchanges = new ArrayList<>();
        int i = 0;
        while (i < history.size()) {
            ChatMessage msg = history.get(i);
            if (msg.getRole() == ChatMessage.Role.tool_call) {
                // Collect tool_call + all subsequent tool responses
                List<ChatMessage> group = new ArrayList<>();
                group.add(msg);
                i++;
                while (i < history.size() && history.get(i).getRole() == ChatMessage.Role.tool) {
                    group.add(history.get(i));
                    i++;
                }
                exchanges.add(new Exchange(group, ExchangeType.TOOL_EXCHANGE));
            } else if (msg.getRole() == ChatMessage.Role.tool) {
                // Orphaned tool message (standalone from TOOL_TASK_TYPES path)
                exchanges.add(new Exchange(List.of(msg), ExchangeType.TOOL_EXCHANGE));
                i++;
            } else if (msg.getRole() == ChatMessage.Role.assistant) {
                exchanges.add(new Exchange(List.of(msg), ExchangeType.ASSISTANT_TEXT));
                i++;
            } else if (msg.getRole() == ChatMessage.Role.user) {
                exchanges.add(new Exchange(List.of(msg), ExchangeType.USER_MESSAGE));
                i++;
            } else {
                exchanges.add(new Exchange(List.of(msg), ExchangeType.OTHER));
                i++;
            }
        }
        return exchanges;
    }

    /**
     * Build a structured summary of older exchanges.
     */
    String buildSummary(List<Exchange> olderExchanges) {
        StringBuilder sb = new StringBuilder();
        sb.append("[Earlier conversation condensed]\n\n");

        int toolCount = 0;
        int textCount = 0;

        for (Exchange ex : olderExchanges) {
            switch (ex.type()) {
                case TOOL_EXCHANGE -> {
                    toolCount++;
                    summarizeToolExchange(sb, ex);
                }
                case ASSISTANT_TEXT -> {
                    textCount++;
                    String text = ex.messages().get(0).getMessage();
                    if (text != null && !text.isEmpty()) {
                        sb.append("- Response: ")
                                .append(truncate(text, SUMMARY_TEXT_LIMIT))
                                .append("\n");
                    }
                }
                case USER_MESSAGE -> {
                    String text = ex.messages().get(0).getMessage();
                    if (text != null && !text.isEmpty()) {
                        sb.append("- User: ")
                                .append(truncate(text, SUMMARY_TEXT_LIMIT))
                                .append("\n");
                    }
                }
                default -> {
                    /* skip */
                }
            }
        }

        sb.append("\n[End of condensed context — ")
                .append(toolCount)
                .append(" tool exchange(s), ")
                .append(textCount)
                .append(" assistant response(s) condensed]");

        return sb.toString();
    }

    private void summarizeToolExchange(StringBuilder sb, Exchange ex) {
        ChatMessage first = ex.messages().get(0);

        if (first.getRole() == ChatMessage.Role.tool_call && first.getToolCalls() != null) {
            List<String> toolNames = first.getToolCalls().stream()
                    .map(ToolCall::getName)
                    .filter(Objects::nonNull)
                    .toList();
            sb.append("- Called tools: ").append(String.join(", ", toolNames));

            // Summarize each tool response
            for (int i = 1; i < ex.messages().size(); i++) {
                ChatMessage toolResponse = ex.messages().get(i);
                if (toolResponse.getToolCalls() != null
                        && !toolResponse.getToolCalls().isEmpty()) {
                    ToolCall tc = toolResponse.getToolCalls().get(0);
                    String output = tc.getOutput() != null ? tc.getOutput().toString() : "";
                    sb.append("\n  ")
                            .append(tc.getName())
                            .append(": ")
                            .append(truncate(output, TOOL_OUTPUT_SUMMARY_LIMIT));
                }
            }
        } else if (first.getRole() == ChatMessage.Role.tool) {
            // Orphaned tool message
            if (first.getToolCalls() != null && !first.getToolCalls().isEmpty()) {
                ToolCall tc = first.getToolCalls().get(0);
                String output = tc.getOutput() != null ? tc.getOutput().toString() : "";
                sb.append("- Tool ")
                        .append(tc.getName())
                        .append(": ")
                        .append(truncate(output, TOOL_OUTPUT_SUMMARY_LIMIT));
            }
        }
        sb.append("\n");
    }

    static String truncate(String text, int maxLen) {
        if (text == null) return "";
        if (text.length() <= maxLen) return text;
        return text.substring(0, maxLen) + "...";
    }

    // ── SUB_WORKFLOW helpers ─────────────────────────────────────────

    /**
     * Extract clean result from SUB_WORKFLOW output.
     * SUB_WORKFLOW outputData = {subWorkflowId, result, finishReason, rejectionReason}
     * We extract just {result: "the actual text"}.
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> extractSubWorkflowResult(Map<String, Object> outputData) {
        if (outputData == null) {
            return Map.of("result", "");
        }
        Object result = outputData.get("result");
        if (result != null) {
            return Map.of("result", result);
        }
        return outputData;
    }

    /**
     * Extract clean input from SUB_WORKFLOW input.
     * SUB_WORKFLOW inputData = {subWorkflowDefinition, workflowInput: {prompt, session_id}, ...}
     * We extract just the workflowInput (the actual arguments).
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> extractSubWorkflowInput(Map<String, Object> inputData) {
        if (inputData == null) {
            return Map.of();
        }
        Object workflowInput = inputData.get("workflowInput");
        if (workflowInput instanceof Map) {
            return (Map<String, Object>) workflowInput;
        }
        Map<String, Object> clean = new HashMap<>(inputData);
        clean.remove("subWorkflowDefinition");
        return clean;
    }
}
