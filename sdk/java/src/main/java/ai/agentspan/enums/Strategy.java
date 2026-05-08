// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.enums;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * How sub-agents are orchestrated in a multi-agent system.
 */
public enum Strategy {
    @JsonProperty("handoff")
    HANDOFF,

    @JsonProperty("sequential")
    SEQUENTIAL,

    @JsonProperty("parallel")
    PARALLEL,

    @JsonProperty("router")
    ROUTER,

    @JsonProperty("round_robin")
    ROUND_ROBIN,

    @JsonProperty("random")
    RANDOM,

    @JsonProperty("swarm")
    SWARM,

    @JsonProperty("manual")
    MANUAL,

    @JsonProperty("plan_execute")
    PLAN_EXECUTE;

    public String toJsonValue() {
        try {
            return Strategy.class.getField(name())
                .getAnnotation(JsonProperty.class).value();
        } catch (NoSuchFieldException e) {
            return name().toLowerCase();
        }
    }
}
