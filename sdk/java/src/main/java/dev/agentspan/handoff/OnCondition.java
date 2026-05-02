// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.handoff;

import java.util.Map;
import java.util.function.Function;

/**
 * Hand off when a custom callable returns {@code true}.
 *
 * <p>The condition function receives the current agent context map and returns
 * a boolean. Serialized as a worker task — the function is registered as a
 * Conductor worker under the name {@code {agentName}_handoff_{target}}.
 *
 * <pre>{@code
 * new OnCondition("supervisor", ctx -> {
 *     Object iter = ctx.get("iteration");
 *     return iter instanceof Number && ((Number) iter).intValue() > 5;
 * })
 * }</pre>
 */
public class OnCondition extends Handoff {

    private final Function<Map<String, Object>, Boolean> condition;

    public OnCondition(String target, Function<Map<String, Object>, Boolean> condition) {
        super(target);
        this.condition = condition;
    }

    public Function<Map<String, Object>, Boolean> getCondition() {
        return condition;
    }
}
