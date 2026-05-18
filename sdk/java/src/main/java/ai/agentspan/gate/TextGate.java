// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.gate;

/**
 * Stop a sequential pipeline if the agent's output contains the given text.
 *
 * <p>When attached to an agent in a sequential pipeline ({@code agent.then(next)}),
 * the pipeline stops after this agent if its output contains the sentinel text.
 * Otherwise execution continues to the next stage.
 *
 * <p>Compiled entirely server-side (INLINE JavaScript) — no worker round-trip needed.
 *
 * <pre>{@code
 * Agent checker = Agent.builder()
 *     .name("checker")
 *     .model("openai/gpt-4o")
 *     .gate(new TextGate("STOP"))
 *     .build();
 *
 * Agent fixer = Agent.builder().name("fixer").model("openai/gpt-4o").build();
 * Agent pipeline = checker.then(fixer);
 * }</pre>
 */
public class TextGate {

    private final String text;
    private final boolean caseSensitive;

    public TextGate(String text) {
        this(text, true);
    }

    public TextGate(String text, boolean caseSensitive) {
        this.text = text;
        this.caseSensitive = caseSensitive;
    }

    public String getText() {
        return text;
    }

    public boolean isCaseSensitive() {
        return caseSensitive;
    }
}
