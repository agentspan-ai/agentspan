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
    private final boolean caseSensitive;

    public TextMentionTermination(String text) {
        this(text, false);
    }

    public TextMentionTermination(String text, boolean caseSensitive) {
        this.text = text;
        this.caseSensitive = caseSensitive;
    }

    /** Create a TextMentionTermination for the given text (case-insensitive). */
    public static TextMentionTermination of(String text) {
        return new TextMentionTermination(text, false);
    }

    /** Create a TextMentionTermination with explicit case sensitivity. */
    public static TextMentionTermination of(String text, boolean caseSensitive) {
        return new TextMentionTermination(text, caseSensitive);
    }

    public String getText() {
        return text;
    }

    public boolean isCaseSensitive() {
        return caseSensitive;
    }

    @Override
    public Map<String, Object> toMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", "text_mention");
        map.put("text", text);
        map.put("caseSensitive", caseSensitive);
        return map;
    }
}
