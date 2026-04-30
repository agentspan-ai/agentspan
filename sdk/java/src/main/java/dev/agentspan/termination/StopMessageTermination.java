// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.termination;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Terminates when the agent output exactly matches a stop signal (after stripping whitespace).
 *
 * <p>Similar to {@link TextMentionTermination} but uses exact match rather than
 * substring search.
 *
 * <pre>{@code
 * Agent agent = Agent.builder()
 *     .name("my_agent")
 *     .model("openai/gpt-4o")
 *     .termination(StopMessageTermination.of("DONE"))
 *     .build();
 * }</pre>
 */
public class StopMessageTermination extends TerminationCondition {

    private final String stopMessage;

    public StopMessageTermination(String stopMessage) {
        this.stopMessage = stopMessage;
    }

    public static StopMessageTermination of(String stopMessage) {
        return new StopMessageTermination(stopMessage);
    }

    public String getStopMessage() {
        return stopMessage;
    }

    @Override
    public Map<String, Object> toMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", "stop_message");
        map.put("stopMessage", stopMessage);
        return map;
    }
}
