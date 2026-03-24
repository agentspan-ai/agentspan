// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.termination;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Terminates after a maximum number of messages.
 */
public class MaxMessageTermination extends TerminationCondition {
    private final int maxMessages;

    public MaxMessageTermination(int maxMessages) {
        this.maxMessages = maxMessages;
    }

    /** Create a MaxMessageTermination with the given message limit. */
    public static MaxMessageTermination of(int maxMessages) {
        return new MaxMessageTermination(maxMessages);
    }

    public int getMaxMessages() {
        return maxMessages;
    }

    @Override
    public Map<String, Object> toMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", "max_message");
        map.put("maxMessages", maxMessages);
        return map;
    }
}
