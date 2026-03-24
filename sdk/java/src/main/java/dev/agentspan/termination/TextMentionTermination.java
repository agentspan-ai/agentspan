// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.termination;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Terminates when the agent output mentions a specific text.
 */
public class TextMentionTermination extends TerminationCondition {
    private final String text;

    public TextMentionTermination(String text) {
        this.text = text;
    }

    /** Create a TextMentionTermination for the given text. */
    public static TextMentionTermination of(String text) {
        return new TextMentionTermination(text);
    }

    public String getText() {
        return text;
    }

    @Override
    public Map<String, Object> toMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", "text_mention");
        map.put("text", text);
        return map;
    }
}
