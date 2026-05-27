// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Internal helpers for serialising plan-value trees.
 *
 * <p>The plan dataclasses ({@link Op#args}, {@link Generate#context},
 * {@link Validation#args}, {@link Action#args}) take {@code Object} so
 * callers can mix primitives, maps, lists, and {@link Ref}. {@code
 * serializeValue} walks that tree and replaces nested {@code Ref}s with
 * their wire form.
 */
final class PlanValues {
    private PlanValues() {}

    @SuppressWarnings("unchecked")
    static Object serializeValue(Object v) {
        if (v instanceof Ref r) return r.toJson();
        if (v instanceof Map<?, ?> map) {
            Map<String, Object> out = new LinkedHashMap<>();
            for (Map.Entry<?, ?> e : map.entrySet()) {
                out.put(String.valueOf(e.getKey()), serializeValue(e.getValue()));
            }
            return out;
        }
        if (v instanceof List<?> list) {
            List<Object> out = new ArrayList<>(list.size());
            for (Object item : list) out.add(serializeValue(item));
            return out;
        }
        return v;
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> serializeArgs(Map<String, Object> args) {
        return (Map<String, Object>) serializeValue(args);
    }
}
