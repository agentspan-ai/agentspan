// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.handoff;

/**
 * Triggers a handoff when the agent output contains a specific text.
 *
 * <p>Example:
 * <pre>{@code
 * OnTextMention.of("refund", "refund_specialist")
 * }</pre>
 */
public class OnTextMention extends Handoff {
    private final String text;

    public OnTextMention(String text, String target) {
        super(target);
        this.text = text;
    }

    public static OnTextMention of(String text, String target) {
        return new OnTextMention(text, target);
    }

    public String getText() {
        return text;
    }
}
