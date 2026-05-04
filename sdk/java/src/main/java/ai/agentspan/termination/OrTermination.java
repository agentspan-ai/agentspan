// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.termination;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Terminates when ANY of the given conditions are met.
 */
public class OrTermination extends TerminationCondition {
    private final TerminationCondition left;
    private final TerminationCondition right;

    public OrTermination(TerminationCondition left, TerminationCondition right) {
        this.left = left;
        this.right = right;
    }

    public TerminationCondition getLeft() { return left; }
    public TerminationCondition getRight() { return right; }

    @Override
    public Map<String, Object> toMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", "or");
        map.put("conditions", Arrays.asList(left.toMap(), right.toMap()));
        return map;
    }
}
