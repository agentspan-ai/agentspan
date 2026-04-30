// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.openai;

import dev.agentspan.model.AgentResult;

/**
 * OpenAI Agents SDK compatible result — drop-in replacement for {@code openai-agents} RunResult.
 *
 * <p>Change one import line:
 * <pre>
 * // Before: import com.openai.agents.RunResult;
 * // After:
 * import dev.agentspan.openai.RunResult;
 * </pre>
 */
public class RunResult {

    private final AgentResult agentResult;

    public RunResult(AgentResult agentResult) {
        this.agentResult = agentResult;
    }

    /** The agent's final text output — same attribute as openai-agents RunResult. */
    public Object getFinalOutput() {
        Object output = agentResult.getOutput();
        if (output instanceof java.util.Map) {
            Object result = ((java.util.Map<?, ?>) output).get("result");
            return result != null ? result : output;
        }
        return output;
    }

    /** The Agentspan execution ID for debugging. */
    public String getExecutionId() {
        return agentResult.getWorkflowId();
    }

    /** The underlying AgentResult. */
    public AgentResult getAgentResult() {
        return agentResult;
    }

    @Override
    public String toString() {
        return "RunResult{finalOutput=" + getFinalOutput() + "}";
    }
}
