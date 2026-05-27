// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import java.util.Map;
import java.util.Objects;

/**
 * A reference to a prior step's whole output.
 *
 * <p>Use {@code new Ref("step_id")} anywhere a literal value would go in an
 * {@link Op}'s {@code args} or a {@link Generate}'s {@code context} to wire
 * one step's output into another step's input — no JSON path, no field
 * selection. The whole result becomes the value at that arg key.
 *
 * <p>The referenced step must be declared in this step's {@code dependsOn}
 * and must exist in the plan; the server rejects the plan at compile time
 * otherwise (no silent broken refs).
 *
 * <p>Self-Refs and Refs to a step not in {@code dependsOn} are compile
 * errors. For a {@code parallel=true} step, the Ref resolves to the array
 * of branch results (the FORK_JOIN aggregator's payload).
 *
 * <p>Serialises to the wire form {@code {"$ref": "<step_id>"}} — same
 * contract as the Python and TypeScript SDKs.
 */
public final class Ref {

    private final String stepId;

    public Ref(String stepId) {
        if (stepId == null || stepId.isEmpty()) {
            throw new IllegalArgumentException("Ref stepId must be a non-empty string");
        }
        this.stepId = stepId;
    }

    public String getStepId() {
        return stepId;
    }

    /** Wire format the server's PAC consumes: {@code {"$ref": "<step_id>"}}. */
    public Map<String, Object> toJson() {
        return Map.of("$ref", stepId);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof Ref other)) return false;
        return Objects.equals(stepId, other.stepId);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(stepId);
    }

    @Override
    public String toString() {
        return "Ref(" + stepId + ")";
    }
}
