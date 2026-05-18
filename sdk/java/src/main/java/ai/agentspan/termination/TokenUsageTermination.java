// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.termination;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Terminates when a token usage threshold is exceeded.
 */
public class TokenUsageTermination extends TerminationCondition {
    private final Integer maxTotalTokens;
    private final Integer maxPromptTokens;
    private final Integer maxCompletionTokens;

    private TokenUsageTermination(Integer maxTotalTokens, Integer maxPromptTokens, Integer maxCompletionTokens) {
        this.maxTotalTokens = maxTotalTokens;
        this.maxPromptTokens = maxPromptTokens;
        this.maxCompletionTokens = maxCompletionTokens;
    }

    /** Terminate when total tokens exceed the limit. */
    public static TokenUsageTermination ofTotal(int maxTotalTokens) {
        return new TokenUsageTermination(maxTotalTokens, null, null);
    }

    /** Terminate when prompt tokens exceed the limit. */
    public static TokenUsageTermination ofPrompt(int maxPromptTokens) {
        return new TokenUsageTermination(null, maxPromptTokens, null);
    }

    /** Terminate when completion tokens exceed the limit. */
    public static TokenUsageTermination ofCompletion(int maxCompletionTokens) {
        return new TokenUsageTermination(null, null, maxCompletionTokens);
    }

    public Integer getMaxTotalTokens() { return maxTotalTokens; }
    public Integer getMaxPromptTokens() { return maxPromptTokens; }
    public Integer getMaxCompletionTokens() { return maxCompletionTokens; }

    @Override
    public Map<String, Object> toMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", "token_usage");
        if (maxTotalTokens != null) map.put("maxTotalTokens", maxTotalTokens);
        if (maxPromptTokens != null) map.put("maxPromptTokens", maxPromptTokens);
        if (maxCompletionTokens != null) map.put("maxCompletionTokens", maxCompletionTokens);
        return map;
    }
}
