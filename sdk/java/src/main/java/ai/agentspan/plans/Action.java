// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import java.util.LinkedHashMap;
import java.util.Map;

/** A tool call attached to {@code on_success} or {@code on_failure}. */
public final class Action {
    private final String tool;
    private final Map<String, Object> args;

    private Action(Builder b) {
        this.tool = b.tool;
        this.args = b.args;
    }

    public Map<String, Object> toJson() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("tool", tool);
        if (args != null) out.put("args", PlanValues.serializeArgs(args));
        return out;
    }

    public static Builder builder(String tool) {
        return new Builder(tool);
    }

    public static final class Builder {
        private final String tool;
        private Map<String, Object> args;

        private Builder(String tool) {
            this.tool = tool;
        }

        public Builder args(Map<String, Object> args) {
            this.args = args;
            return this;
        }

        public Action build() {
            return new Action(this);
        }
    }
}
