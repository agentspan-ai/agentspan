// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.memory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Manages conversation history for an agent session.
 *
 * <p>Stores messages in a format compatible with Conductor workflow variables so that conversation
 * state can be persisted across workflow executions.
 *
 * <pre>{@code
 * ConversationMemory memory = new ConversationMemory();
 * memory.addUserMessage("Hello!");
 * memory.addAssistantMessage("Hi there!");
 * List<Map<String, Object>> msgs = memory.toChatMessages();
 * }</pre>
 */
public class ConversationMemory {

    private final List<Map<String, Object>> messages = new ArrayList<>();
    private final Integer maxMessages;

    public ConversationMemory() {
        this.maxMessages = null;
    }

    public ConversationMemory(int maxMessages) {
        this.maxMessages = maxMessages;
    }

    /** Append a user message to the conversation. */
    public void addUserMessage(String content) {
        Map<String, Object> msg = new LinkedHashMap<>();
        msg.put("role", "user");
        msg.put("message", content);
        messages.add(msg);
        trim();
    }

    /** Append an assistant message to the conversation. */
    public void addAssistantMessage(String content) {
        Map<String, Object> msg = new LinkedHashMap<>();
        msg.put("role", "assistant");
        msg.put("message", content);
        messages.add(msg);
        trim();
    }

    /** Append a system message to the conversation. */
    public void addSystemMessage(String content) {
        Map<String, Object> msg = new LinkedHashMap<>();
        msg.put("role", "system");
        msg.put("message", content);
        messages.add(msg);
        trim();
    }

    /** Record a tool call in the conversation. */
    public void addToolCall(String toolName, Map<String, Object> arguments, String taskReferenceName) {
        String ref = taskReferenceName != null ? taskReferenceName : toolName + "_ref";
        Map<String, Object> toolCall = new LinkedHashMap<>();
        toolCall.put("name", toolName);
        toolCall.put("taskReferenceName", ref);
        toolCall.put("input", arguments);

        Map<String, Object> msg = new LinkedHashMap<>();
        msg.put("role", "tool_call");
        msg.put("message", "");
        msg.put("tool_calls", List.of(toolCall));
        messages.add(msg);
        trim();
    }

    /** Record a tool result in the conversation. */
    public void addToolResult(String toolName, Object result, String taskReferenceName) {
        String ref = taskReferenceName != null ? taskReferenceName : toolName + "_ref";
        Map<String, Object> msg = new LinkedHashMap<>();
        msg.put("role", "tool");
        msg.put("message", result != null ? result.toString() : "");
        msg.put("toolCallId", ref);
        msg.put("taskReferenceName", ref);
        messages.add(msg);
        trim();
    }

    /** Return a deep copy of messages in Conductor ChatMessage format. */
    public List<Map<String, Object>> toChatMessages() {
        List<Map<String, Object>> copy = new ArrayList<>(messages.size());
        for (Map<String, Object> msg : messages) {
            copy.add(new LinkedHashMap<>(msg));
        }
        return copy;
    }

    /** Number of messages currently stored. */
    public int size() {
        return messages.size();
    }

    /** Remove all messages. */
    public void clear() {
        messages.clear();
    }

    private void trim() {
        if (maxMessages != null) {
            while (messages.size() > maxMessages) {
                messages.remove(0);
            }
        }
    }
}
