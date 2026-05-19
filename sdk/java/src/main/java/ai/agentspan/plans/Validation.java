// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * A post-execution check. Runs after all {@link Step}s complete. PAC routes
 * the workflow to {@code on_success} when every validation passes, else to
 * {@code on_failure}.
 */
public final class Validation {
    private final String tool;
    private final Map<String, Object> args;
    private final String successCondition;

    private Validation(Builder b) {
        this.tool = b.tool;
        this.args = b.args;
        this.successCondition = b.successCondition;
    }

    public Map<String, Object> toJson() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("tool", tool);
        if (args != null) out.put("args", PlanValues.serializeArgs(args));
        if (successCondition != null) out.put("success_condition", successCondition);
        return out;
    }

    public static Builder builder(String tool) {
        return new Builder(tool);
    }

    public static final class Builder {
        private final String tool;
        private Map<String, Object> args;
        private String successCondition;

        private Builder(String tool) {
            this.tool = tool;
        }

        public Builder args(Map<String, Object> args) {
            this.args = args;
            return this;
        }

        /**
         * Optional JS expression evaluated against the tool's output ({@code $}
         * is the parsed output map). Returns truthy on pass.
         */
        public Builder successCondition(String expr) {
            this.successCondition = expr;
            return this;
        }

        public Validation build() {
            return new Validation(this);
        }
    }
}
