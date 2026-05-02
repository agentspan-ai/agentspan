// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.guardrail;

import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.model.GuardrailDef;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * A guardrail that uses an LLM to evaluate content against a policy.
 *
 * <p>Serialized as {@code guardrailType: "llm"}. The Conductor server calls the specified model
 * with the policy and content and expects a {@code {"passed": true/false, "reason": "..."}} response.
 * No worker process is needed.
 *
 * <pre>{@code
 * GuardrailDef safety = LLMGuardrail.builder()
 *     .name("safety_check")
 *     .model("openai/gpt-4o-mini")
 *     .policy("Reject any content that contains harmful, violent, or discriminatory language.")
 *     .build();
 * }</pre>
 */
public class LLMGuardrail {

    private LLMGuardrail() {}

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private String name = "llm_guardrail";
        private String model;
        private String policy;
        private Position position = Position.OUTPUT;
        private OnFail onFail = OnFail.RETRY;
        private int maxRetries = 3;
        private Integer maxTokens;

        public Builder name(String name) { this.name = name; return this; }

        /** LLM model in {@code "provider/model"} format (e.g. {@code "openai/gpt-4o-mini"}). */
        public Builder model(String model) { this.model = model; return this; }

        /** Description of what the guardrail should check for. */
        public Builder policy(String policy) { this.policy = policy; return this; }

        public Builder position(Position position) { this.position = position; return this; }

        public Builder onFail(OnFail onFail) { this.onFail = onFail; return this; }

        public Builder maxRetries(int maxRetries) { this.maxRetries = maxRetries; return this; }

        public Builder maxTokens(int maxTokens) { this.maxTokens = maxTokens; return this; }

        public GuardrailDef build() {
            if (model == null || model.isEmpty()) {
                throw new IllegalArgumentException("LLMGuardrail requires a model");
            }
            if (policy == null || policy.isEmpty()) {
                throw new IllegalArgumentException("LLMGuardrail requires a policy");
            }
            Map<String, Object> config = new LinkedHashMap<>();
            config.put("model", model);
            config.put("policy", policy);
            if (maxTokens != null) config.put("maxTokens", maxTokens);
            return GuardrailDef.builder()
                    .name(name)
                    .position(position)
                    .onFail(onFail)
                    .maxRetries(maxRetries)
                    .guardrailType("llm")
                    .config(config)
                    .build();
        }
    }
}
