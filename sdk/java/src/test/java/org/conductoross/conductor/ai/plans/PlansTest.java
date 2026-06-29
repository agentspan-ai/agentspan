// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.plans;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import org.junit.jupiter.api.Test;

/** Pure unit tests for the PLAN_EXECUTE DSL builders (no server). */
class PlansTest {

    @Test
    void refCarriesStepIdAndEquals() {
        Ref r = new Ref("step1");
        assertEquals("step1", r.getStepId());
        assertNotNull(r.toJson());
        assertEquals(new Ref("step1"), r);
        assertNotEquals(new Ref("other"), r);
    }

    @Test
    void opSerializes() {
        Op op = Op.builder("git").args(Map.of("cmd", "status")).build();
        Map<String, Object> json = op.toJson();
        assertNotNull(json);
        assertFalse(json.isEmpty());
    }

    @Test
    void actionSerializes() {
        assertNotNull(Action.builder("notify").args(Map.of("msg", "hi")).build().toJson());
    }

    @Test
    void opRequiresExactlyOneOfArgsOrGenerate() {
        // Invariant enforced in Op's constructor.
        assertThrows(IllegalArgumentException.class, () -> Op.builder("git").build());
    }

    @Test
    void stepWithOperationSerializes() {
        Step s = Step.builder("s1")
                .operation(Op.builder("git").args(Map.of("cmd", "status")).build())
                .build();
        assertNotNull(s.toJson());
    }

    @Test
    void stepParallelAndDependsOn() {
        Step s = Step.builder("s2")
                .parallel(true)
                .dependsOn("s1")
                .operation(Op.builder("x").args(Map.of("k", "v")).build())
                .build();
        assertNotNull(s.toJson());
    }

    @Test
    void planWithStepsSerializesToJson() {
        Plan plan = Plan.builder()
                .step(Step.builder("s1")
                        .operation(
                                Op.builder("git").args(Map.of("cmd", "status")).build())
                        .build())
                .build();
        Map<String, Object> json = plan.toJson();
        assertNotNull(json);
        assertTrue(json.containsKey("steps"), "plan json should expose its steps; got keys: " + json.keySet());
    }
}
