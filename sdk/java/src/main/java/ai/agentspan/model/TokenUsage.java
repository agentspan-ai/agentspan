// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.model;

/**
 * Aggregated token usage across all LLM calls in an agent execution.
 */
public class TokenUsage {
    private final int promptTokens;
    private final int completionTokens;
    private final int totalTokens;

    public TokenUsage(int promptTokens, int completionTokens, int totalTokens) {
        this.promptTokens = promptTokens;
        this.completionTokens = completionTokens;
        this.totalTokens = totalTokens;
    }

    public int getPromptTokens() {
        return promptTokens;
    }

    public int getCompletionTokens() {
        return completionTokens;
    }

    public int getTotalTokens() {
        return totalTokens;
    }

    @Override
    public String toString() {
        return "TokenUsage{prompt=" + promptTokens + ", completion=" + completionTokens
                + ", total=" + totalTokens + "}";
    }
}
