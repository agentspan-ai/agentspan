// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * A compiled plan ready for {@code Strategy.PLAN_EXECUTE} execution.
 *
 * <p>Construct via {@link #builder()} or pass to
 * {@code AgentRuntime.run(harness, prompt, plan)} to skip the planner LLM
 * and run a fully deterministic pipeline.
 *
 * <p>The {@code toJson()} output is the wire format PAC consumes —
 * identical to what the Python {@code agentspan.agents.plans.Plan} and
 * TypeScript {@code Plan} emit.
 */
public final class Plan {
    private final List<Step> steps;
    private final List<Validation> validation;
    private final List<Action> onSuccess;
    private final List<Action> onFailure;

    private Plan(Builder b) {
        this.steps = List.copyOf(b.steps);
        this.validation = List.copyOf(b.validation);
        this.onSuccess = List.copyOf(b.onSuccess);
        this.onFailure = List.copyOf(b.onFailure);
    }

    public Map<String, Object> toJson() {
        Map<String, Object> out = new LinkedHashMap<>();
        List<Map<String, Object>> stepJsons = new ArrayList<>(steps.size());
        for (Step s : steps) stepJsons.add(s.toJson());
        out.put("steps", stepJsons);
        if (!validation.isEmpty()) {
            List<Map<String, Object>> vj = new ArrayList<>(validation.size());
            for (Validation v : validation) vj.add(v.toJson());
            out.put("validation", vj);
        }
        if (!onSuccess.isEmpty()) {
            List<Map<String, Object>> aj = new ArrayList<>(onSuccess.size());
            for (Action a : onSuccess) aj.add(a.toJson());
            out.put("on_success", aj);
        }
        if (!onFailure.isEmpty()) {
            List<Map<String, Object>> aj = new ArrayList<>(onFailure.size());
            for (Action a : onFailure) aj.add(a.toJson());
            out.put("on_failure", aj);
        }
        return out;
    }

    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private final List<Step> steps = new ArrayList<>();
        private final List<Validation> validation = new ArrayList<>();
        private final List<Action> onSuccess = new ArrayList<>();
        private final List<Action> onFailure = new ArrayList<>();

        public Builder step(Step s) {
            steps.add(s);
            return this;
        }

        public Builder steps(List<Step> ss) {
            steps.addAll(ss);
            return this;
        }

        public Builder validation(Validation v) {
            validation.add(v);
            return this;
        }

        public Builder onSuccess(Action a) {
            onSuccess.add(a);
            return this;
        }

        public Builder onFailure(Action a) {
            onFailure.add(a);
            return this;
        }

        public Plan build() {
            return new Plan(this);
        }
    }
}
