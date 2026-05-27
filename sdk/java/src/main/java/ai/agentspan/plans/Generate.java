// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * LLM-generated arguments for a tool call inside a plan step.
 *
 * <p>When an {@link Op} carries {@code generate}, the server emits an
 * LLM call at run time that produces the tool's args from these
 * instructions, then runs the tool with the generated args. Use this
 * when arg values aren't known at plan-construction time.
 */
public final class Generate {
    private final String instructions;
    private final String outputSchema;
    private final Integer maxTokens;
    private final Object context;

    private Generate(Builder b) {
        this.instructions = b.instructions;
        this.outputSchema = b.outputSchema;
        this.maxTokens = b.maxTokens;
        this.context = b.context;
    }

    public Map<String, Object> toJson() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("instructions", instructions);
        out.put("output_schema", outputSchema);
        if (maxTokens != null) out.put("max_tokens", maxTokens);
        if (context != null) out.put("context", PlanValues.serializeValue(context));
        return out;
    }

    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private String instructions;
        private String outputSchema;
        private Integer maxTokens;
        private Object context;

        public Builder instructions(String s) {
            this.instructions = s;
            return this;
        }

        public Builder outputSchema(String s) {
            this.outputSchema = s;
            return this;
        }

        public Builder maxTokens(int n) {
            this.maxTokens = n;
            return this;
        }

        /**
         * Optional extra text appended to the LLM's user message. Accepts
         * a plain string or a {@link Ref} — when a {@code Ref} is passed
         * the server substitutes the upstream step's output at run time.
         */
        public Builder context(Object o) {
            this.context = o;
            return this;
        }

        public Generate build() {
            if (instructions == null || outputSchema == null) {
                throw new IllegalStateException("Generate requires instructions and outputSchema");
            }
            return new Generate(this);
        }
    }
}
