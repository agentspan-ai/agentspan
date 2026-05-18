/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.compiler;

import java.util.LinkedHashMap;
import java.util.Map;

import com.netflix.conductor.common.metadata.workflow.WorkflowTask;

import dev.agentspan.runtime.util.JavaScriptBuilder;

/**
 * Compiles gate conditions into Conductor workflow tasks.
 *
 * <p>A gate is a conditional check inserted between sequential pipeline stages.
 * If the gate evaluates to "stop", the pipeline ends early; otherwise it continues.</p>
 *
 * <p>{@code TextGate} (type "text_contains") is compiled to an INLINE JavaScript task
 * — no worker round-trip needed. Callable gates are compiled to SIMPLE tasks
 * that delegate to a Python SDK worker.</p>
 */
public class GateCompiler {

    /**
     * Compile a gate configuration into a workflow task.
     * Returns a task whose output is {@code {decision: "continue" | "stop"}}.
     *
     * @param gateConfig   the gate configuration map from AgentConfig
     * @param refName      task reference name for the gate task
     * @param prevOutputRef Conductor expression referencing the previous stage's output
     * @return a fully configured WorkflowTask
     */
    @SuppressWarnings("unchecked")
    public static WorkflowTask compileGate(Map<String, Object> gateConfig, String refName, String prevOutputRef) {

        String type = (String) gateConfig.get("type");

        if ("text_contains".equals(type)) {
            return compileTextContainsGate(gateConfig, refName, prevOutputRef);
        }

        // Callable gate: SIMPLE task for SDK worker
        if (gateConfig.containsKey("taskName")) {
            return compileWorkerGate(gateConfig, refName, prevOutputRef);
        }

        throw new IllegalArgumentException("Unknown gate type: " + type);
    }

    private static WorkflowTask compileTextContainsGate(
            Map<String, Object> config, String refName, String prevOutputRef) {

        String text = (String) config.get("text");
        Object caseSensitiveObj = config.getOrDefault("caseSensitive", true);
        boolean caseSensitive = caseSensitiveObj instanceof Boolean ? (Boolean) caseSensitiveObj : true;

        String script = JavaScriptBuilder.iife(
                "var content = String($.result || '');" + (caseSensitive ? "" : "content = content.toLowerCase();")
                        + "var sentinel = "
                        + JavaScriptBuilder.toJson(caseSensitive ? text : text.toLowerCase()) + ";"
                        + "var found = content.indexOf(sentinel) >= 0;"
                        + "return {decision: found ? 'stop' : 'continue'};");

        WorkflowTask task = new WorkflowTask();
        task.setType("INLINE");
        task.setTaskReferenceName(refName);

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("evaluatorType", "graaljs");
        inputs.put("expression", script);
        inputs.put("result", prevOutputRef);
        task.setInputParameters(inputs);

        return task;
    }

    private static WorkflowTask compileWorkerGate(Map<String, Object> config, String refName, String prevOutputRef) {

        WorkflowTask task = new WorkflowTask();
        task.setType("SIMPLE");
        task.setName((String) config.get("taskName"));
        task.setTaskReferenceName(refName);

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("result", prevOutputRef);
        task.setInputParameters(inputs);

        return task;
    }
}
