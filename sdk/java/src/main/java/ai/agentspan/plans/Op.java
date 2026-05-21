// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * A single tool invocation within a plan step.
 *
 * <p>Exactly one of {@code args} or {@code generate} should be set.
 * {@code args} runs the tool deterministically with literal values;
 * {@code generate} defers arg construction to a per-op LLM call at run
 * time.
 */
public final class Op {
    private final String tool;
    private final Map<String, Object> args;
    private final Generate generate;

    private Op(Builder b) {
        if ((b.args == null) == (b.generate == null)) {
            throw new IllegalArgumentException(
                    "Op('" + b.tool + "'): exactly one of args or generate must be set");
        }
        this.tool = b.tool;
        this.args = b.args;
        this.generate = b.generate;
    }

    public Map<String, Object> toJson() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("tool", tool);
        if (args != null) out.put("args", PlanValues.serializeArgs(args));
        if (generate != null) out.put("generate", generate.toJson());
        return out;
    }

    public static Builder builder(String tool) {
        return new Builder(tool);
    }

    public static final class Builder {
        private final String tool;
        private Map<String, Object> args;
        private Generate generate;

        private Builder(String tool) {
            this.tool = tool;
        }

        public Builder args(Map<String, Object> args) {
            this.args = args;
            return this;
        }

        public Builder generate(Generate g) {
            this.generate = g;
            return this;
        }

        public Op build() {
            return new Op(this);
        }
    }
}
