/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.compiler;

import com.netflix.conductor.common.metadata.workflow.WorkflowTask;
import lombok.AllArgsConstructor;
import lombok.Data;
import dev.agentspan.runtime.model.GuardrailConfig;
import dev.agentspan.runtime.util.JavaScriptBuilder;
import dev.agentspan.runtime.util.ModelParser;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Compiles guardrail configurations into Conductor workflow tasks.
 *
 * <p>Mirrors the guardrail compilation logic from Python's {@code agent_compiler.py}.
 * Each guardrail type compiles to a different task structure:
 * <ul>
 *   <li><b>RegexGuardrail</b> - InlineTask (JavaScript regex, server-side)</li>
 *   <li><b>LLMGuardrail</b> - LlmChatComplete + InlineTask (server-side LLM judge)</li>
 *   <li><b>Custom guardrail</b> - SimpleTask (references worker task)</li>
 *   <li><b>External guardrail</b> - SimpleTask (references remote worker)</li>
 * </ul>
 */
public class GuardrailCompiler {

    /**
     * Result of compiling a single guardrail into workflow tasks.
     */
    @Data
    @AllArgsConstructor
    public static class GuardrailTaskResult {
        private List<WorkflowTask> tasks;
        private String refName;
        private boolean isInline;
    }

    /**
     * Result of compiling guardrail routing (switch task + retry ref).
     */
    @Data
    @AllArgsConstructor
    public static class GuardrailRoutingResult {
        private WorkflowTask switchTask;
        private String retryRef;
    }

    /**
     * Compile output guardrails into workflow tasks.
     *
     * <p>Filters to {@code position == "output"} guardrails, then partitions by type
     * and compiles each into the appropriate task structure.
     *
     * @param guardrails  List of guardrail configurations.
     * @param agentName   Name of the owning agent (used for ref name prefixes).
     * @param contentRef  Conductor expression referencing the LLM output content
     *                    (e.g. {@code ${agentName_llm.output.result}}).
     * @return List of {@link GuardrailTaskResult} entries, one per output guardrail.
     */
    public List<GuardrailTaskResult> compileGuardrailTasks(
            List<GuardrailConfig> guardrails, String agentName, String contentRef) {

        if (guardrails == null || guardrails.isEmpty()) {
            return new ArrayList<>();
        }

        // Filter to output guardrails only
        List<GuardrailConfig> outputGuardrails = guardrails.stream()
                .filter(g -> "output".equals(g.getPosition()))
                .toList();

        if (outputGuardrails.isEmpty()) {
            return new ArrayList<>();
        }

        String iterationRef = "${" + agentName + "_loop.iteration}";
        return compileGuardrailTasksInternal(outputGuardrails, agentName, contentRef, iterationRef);
    }

    /**
     * Compile tool-level guardrails into workflow tasks.
     *
     * <p>Unlike {@link #compileGuardrailTasks}, this method does not filter by position
     * and uses a {@code "_tool"} prefix in ref names to avoid collisions with agent-level
     * guardrails.</p>
     *
     * @param guardrails  List of guardrail configurations from tool definitions.
     * @param agentName   Name of the owning agent.
     * @param contentRef  Conductor expression referencing the formatted tool call content.
     * @return List of {@link GuardrailTaskResult} entries, one per guardrail.
     */
    public List<GuardrailTaskResult> compileToolGuardrailTasks(
            List<GuardrailConfig> guardrails, String agentName, String contentRef) {

        if (guardrails == null || guardrails.isEmpty()) {
            return new ArrayList<>();
        }

        // Tool guardrails use a fixed iteration ref since retry is handled by the outer DoWhile
        return compileGuardrailTasksInternal(guardrails, agentName + "_tool", contentRef, "1");
    }

    /**
     * Internal helper that compiles guardrails without position filtering.
     */
    private List<GuardrailTaskResult> compileGuardrailTasksInternal(
            List<GuardrailConfig> guardrails, String prefix, String contentRef, String iterationRef) {

        List<GuardrailTaskResult> results = new ArrayList<>();

        for (GuardrailConfig guard : guardrails) {
            String type = guard.getGuardrailType();
            if (type == null) {
                continue;
            }

            switch (type) {
                case "regex" -> results.add(compileRegexGuardrail(guard, prefix, contentRef, iterationRef));
                case "llm" -> results.add(compileLlmGuardrail(guard, prefix, contentRef, iterationRef));
                case "custom" -> results.add(compileCustomGuardrail(guard, prefix, contentRef, iterationRef));
                case "external" -> results.add(compileExternalGuardrail(guard, prefix, contentRef, iterationRef));
            }
        }

        return results;
    }

    /**
     * Compile a RegexGuardrail into an InlineTask.
     */
    private GuardrailTaskResult compileRegexGuardrail(
            GuardrailConfig guard, String agentName, String contentRef, String iterationRef) {

        String refName = agentName + "_regex_guardrail_" + guard.getName();
        String patternsJson = JavaScriptBuilder.toJson(guard.getPatterns());
        String mode = guard.getMode() != null ? guard.getMode() : "block";
        String onFail = guard.getOnFail() != null ? guard.getOnFail() : "retry";
        String message = guard.getMessage();
        if (message == null) {
            message = "block".equals(mode)
                    ? "Content matched a blocked pattern."
                    : "Content did not match any allowed pattern.";
        }
        int maxRetries = guard.getMaxRetries();
        String guardrailName = guard.getName();

        String script = JavaScriptBuilder.regexGuardrailScript(
                patternsJson, mode, onFail, message, maxRetries, guardrailName);

        WorkflowTask task = new WorkflowTask();
        task.setTaskReferenceName(refName);
        task.setType("INLINE");

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("evaluatorType", "graaljs");
        inputs.put("expression", script);
        inputs.put("content", contentRef);
        inputs.put("iteration", iterationRef);
        task.setInputParameters(inputs);

        return new GuardrailTaskResult(List.of(task), refName, true);
    }

    /**
     * Compile an LLMGuardrail into an LlmChatComplete task + InlineTask parser.
     */
    private GuardrailTaskResult compileLlmGuardrail(
            GuardrailConfig guard, String agentName, String contentRef, String iterationRef) {

        String refName = agentName + "_llm_guardrail_" + guard.getName();
        String llmRef = refName + "_llm";

        ModelParser.ParsedModel parsed = ModelParser.parse(guard.getModel());

        // Task 1: LLM_CHAT_COMPLETE - judge LLM evaluates content
        String policyPrompt = "You are a content safety evaluator. Evaluate the following "
                + "content against this policy:\n\n"
                + "POLICY: " + guard.getPolicy() + "\n\n"
                + "Respond with ONLY a JSON object: {\"passed\": true/false, \"reason\": \"...\"}";

        WorkflowTask llmTask = new WorkflowTask();
        llmTask.setName("LLM_CHAT_COMPLETE");
        llmTask.setTaskReferenceName(llmRef);
        llmTask.setType("LLM_CHAT_COMPLETE");

        Map<String, Object> llmInputs = new LinkedHashMap<>();
        llmInputs.put("llmProvider", parsed.getProvider());
        llmInputs.put("model", parsed.getModel());
        llmInputs.put("messages", List.of(
                Map.of("role", "system", "message", policyPrompt),
                Map.of("role", "user", "message", contentRef)
        ));
        llmInputs.put("temperature", 0);
        llmInputs.put("maxTokens", guard.getMaxTokens() != null ? guard.getMaxTokens() : 256);
        llmInputs.put("jsonOutput", true);
        llmTask.setInputParameters(llmInputs);

        // Task 2: InlineTask parser - parse LLM JSON into guardrail schema
        String onFail = guard.getOnFail() != null ? guard.getOnFail() : "retry";
        int maxRetries = guard.getMaxRetries();
        String guardrailName = guard.getName();

        String parserScript = JavaScriptBuilder.llmGuardrailParserScript(onFail, maxRetries, guardrailName);

        WorkflowTask parserTask = new WorkflowTask();
        parserTask.setTaskReferenceName(refName);
        parserTask.setType("INLINE");

        Map<String, Object> parserInputs = new LinkedHashMap<>();
        parserInputs.put("evaluatorType", "graaljs");
        parserInputs.put("expression", parserScript);
        parserInputs.put("llm_result", "${" + llmRef + ".output.result}");
        parserInputs.put("iteration", iterationRef);
        parserTask.setInputParameters(parserInputs);

        return new GuardrailTaskResult(List.of(llmTask, parserTask), refName, true);
    }

    /**
     * Compile a custom guardrail into a SimpleTask referencing the worker task.
     */
    private GuardrailTaskResult compileCustomGuardrail(
            GuardrailConfig guard, String agentName, String contentRef, String iterationRef) {

        String refName = agentName + "_output_guardrail";

        WorkflowTask task = new WorkflowTask();
        task.setName(guard.getTaskName());
        task.setTaskReferenceName(refName);
        task.setType("SIMPLE");

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("content", contentRef);
        inputs.put("iteration", iterationRef);
        task.setInputParameters(inputs);

        return new GuardrailTaskResult(List.of(task), refName, false);
    }

    /**
     * Compile an external guardrail into a SimpleTask referencing the remote worker.
     */
    private GuardrailTaskResult compileExternalGuardrail(
            GuardrailConfig guard, String agentName, String contentRef, String iterationRef) {

        String refName = agentName + "_ext_guardrail_" + guard.getName();

        WorkflowTask task = new WorkflowTask();
        task.setName(guard.getName());
        task.setTaskReferenceName(refName);
        task.setType("SIMPLE");

        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("content", contentRef);
        inputs.put("iteration", iterationRef);
        task.setInputParameters(inputs);

        return new GuardrailTaskResult(List.of(task), refName, false);
    }

    /**
     * Build a SwitchTask that routes based on the guardrail result's {@code on_fail} field.
     *
     * <p>Routes to different handling based on the failure action:
     * <ul>
     *   <li><b>retry</b> - InlineTask with retry feedback message for the LLM</li>
     *   <li><b>raise</b> - TerminateTask with FAILED status</li>
     *   <li><b>fix</b> - InlineTask passing through fixed_output</li>
     *   <li><b>human</b> - HumanTask + validate + normalize + process + inner switch</li>
     *   <li><b>default (pass)</b> - SetVariable no-op</li>
     * </ul>
     *
     * @param guard        The guardrail configuration.
     * @param guardrailRef Task reference name of the guardrail task.
     * @param contentRef   Conductor expression referencing the LLM output content.
     * @param agentName    Name of the owning agent.
     * @param suffix       Suffix for uniqueness when multiple guardrails exist.
     * @param isInline     True if the guardrail task is an InlineTask (output.result.*),
     *                     false for worker/SimpleTask (output.*).
     * @return A {@link GuardrailRoutingResult} containing the switch task and retry ref.
     */
    public GuardrailRoutingResult compileGuardrailRouting(
            GuardrailConfig guard, String guardrailRef, String contentRef,
            String agentName, String suffix, boolean isInline) {
        return compileGuardrailRouting(guard, guardrailRef, contentRef, agentName, suffix, isInline, null);
    }

    public GuardrailRoutingResult compileGuardrailRouting(
            GuardrailConfig guard, String guardrailRef, String contentRef,
            String agentName, String suffix, boolean isInline, String agentModel) {

        // InlineTask outputs live under output.result.*; worker outputs at output.*
        String outPath = isInline
                ? guardrailRef + ".output.result"
                : guardrailRef + ".output";

        String s = suffix;

        // --- SwitchTask (value-based, not JavaScript) ---
        WorkflowTask sw = new WorkflowTask();
        sw.setType("SWITCH");
        sw.setTaskReferenceName(agentName + "_guardrail_route" + s);
        sw.setEvaluatorType("value-param");
        sw.setExpression("switchCaseValue");

        Map<String, Object> switchInputs = new LinkedHashMap<>();
        switchInputs.put("switchCaseValue", "${" + outPath + ".on_fail}");
        sw.setInputParameters(switchInputs);

        Map<String, List<WorkflowTask>> decisionCases = new LinkedHashMap<>();

        // --- "retry" case: InlineTask that formats feedback ---
        String retryRef = agentName + "_guardrail_retry" + s;
        WorkflowTask retryTask = new WorkflowTask();
        retryTask.setTaskReferenceName(retryRef);
        retryTask.setType("INLINE");

        Map<String, Object> retryInputs = new LinkedHashMap<>();
        retryInputs.put("evaluatorType", "graaljs");
        retryInputs.put("expression", JavaScriptBuilder.guardrailRetryScript());
        retryInputs.put("guardrail_message", "${" + outPath + ".message}");
        retryInputs.put("llm_output", contentRef);
        retryTask.setInputParameters(retryInputs);

        decisionCases.put("retry", List.of(retryTask));

        // --- "raise" case: terminate workflow ---
        WorkflowTask terminateTask = new WorkflowTask();
        terminateTask.setType("TERMINATE");
        terminateTask.setTaskReferenceName(agentName + "_guardrail_terminate" + s);

        Map<String, Object> terminateInputs = new LinkedHashMap<>();
        terminateInputs.put("terminationStatus", "FAILED");
        terminateInputs.put("terminationReason", "${" + outPath + ".message}");
        terminateTask.setInputParameters(terminateInputs);

        decisionCases.put("raise", List.of(terminateTask));

        // --- "fix" case: InlineTask that passes through fixed_output + SET_VARIABLE to store it ---
        WorkflowTask fixTask = new WorkflowTask();
        fixTask.setTaskReferenceName(agentName + "_guardrail_fix" + s);
        fixTask.setType("INLINE");

        Map<String, Object> fixInputs = new LinkedHashMap<>();
        fixInputs.put("evaluatorType", "graaljs");
        fixInputs.put("expression", JavaScriptBuilder.guardrailFixScript());
        fixInputs.put("fixed_output", "${" + outPath + ".fixed_output}");
        fixTask.setInputParameters(fixInputs);

        // Store fixed output in workflow variable so post-loop output resolution can use it
        WorkflowTask fixSetVar = new WorkflowTask();
        fixSetVar.setType("SET_VARIABLE");
        fixSetVar.setTaskReferenceName(agentName + "_guardrail_fix_set" + s);
        Map<String, Object> fixSetVarInputs = new LinkedHashMap<>();
        fixSetVarInputs.put("_fixed_output", "${" + outPath + ".fixed_output}");
        fixSetVar.setInputParameters(fixSetVarInputs);

        decisionCases.put("fix", List.of(fixTask, fixSetVar));

        // --- "human" case: HumanTask + validate + normalize + process + inner switch ---
        if ("human".equals(guard.getOnFail())) {
            decisionCases.put("human", compileHumanCase(guard, agentName, contentRef, outPath, s, agentModel));
        }

        sw.setDecisionCases(decisionCases);

        // --- default case (pass): SetVariable no-op ---
        WorkflowTask passNoop = new WorkflowTask();
        passNoop.setType("SET_VARIABLE");
        passNoop.setTaskReferenceName(agentName + "_guardrail_pass_noop" + s);

        Map<String, Object> passInputs = new LinkedHashMap<>();
        passInputs.put("_guardrail_passed", true);
        passNoop.setInputParameters(passInputs);

        sw.setDefaultCase(List.of(passNoop));

        return new GuardrailRoutingResult(sw, retryRef);
    }

    /**
     * Compile the "human" case for guardrail routing.
     *
     * <p>Produces: HumanTask -> validate InlineTask -> normalize SwitchTask
     * (with LLM normalizer) -> process InlineTask -> inner action SwitchTask.
     */
    private List<WorkflowTask> compileHumanCase(
            GuardrailConfig guard, String agentName, String contentRef, String outPath, String s, String agentModel) {

        List<WorkflowTask> humanCaseTasks = new ArrayList<>();
        String humanRef = agentName + "_guardrail_human" + s;

        // --- HumanTask ---
        WorkflowTask humanTask = new WorkflowTask();
        humanTask.setType("HUMAN");
        humanTask.setTaskReferenceName(humanRef);

        Map<String, Object> humanInputs = new LinkedHashMap<>();
        humanInputs.put("__humanTaskDefinition", Map.of(
            "assignmentCompletionStrategy", "LEAVE_OPEN",
            "displayName", agentName + " Guardrail Review",
            "userFormTemplate", Map.of("version", 0)
        ));
        humanInputs.put("guardrail_message", "${" + outPath + ".message}");
        humanInputs.put("guardrail_name", "${" + outPath + ".guardrail_name}");
        humanInputs.put("llm_output", contentRef);
        humanInputs.put("response_schema", Map.of(
                "type", "object",
                "required", List.of("approved"),
                "properties", Map.of(
                        "approved", Map.of(
                                "type", "boolean",
                                "title", "Approved",
                                "description", "Approve or reject the LLM output"
                        ),
                        "edited_output", Map.of(
                                "type", "string",
                                "title", "Edited Output",
                                "description", "Provide corrected output if editing"
                        ),
                        "reason", Map.of(
                                "type", "string",
                                "title", "Reason",
                                "description", "Reason for rejection"
                        )
                )
        ));
        humanInputs.put("response_ui_schema", Map.of(
                "ui:order", List.of("approved", "edited_output", "reason"),
                "approved", Map.of("ui:widget", "radio"),
                "edited_output", Map.of("ui:widget", "textarea"),
                "reason", Map.of("ui:widget", "textarea")
        ));
        humanTask.setInputParameters(humanInputs);
        humanCaseTasks.add(humanTask);

        // --- Validate InlineTask: parse & coerce simple cases ---
        String validateRef = agentName + "_guardrail_human_validate" + s;
        WorkflowTask validateTask = new WorkflowTask();
        validateTask.setTaskReferenceName(validateRef);
        validateTask.setType("INLINE");

        Map<String, Object> validateInputs = new LinkedHashMap<>();
        validateInputs.put("evaluatorType", "graaljs");
        validateInputs.put("expression", JavaScriptBuilder.humanValidateScript());
        validateInputs.put("human_output", "${" + humanRef + ".output}");
        validateTask.setInputParameters(validateInputs);
        humanCaseTasks.add(validateTask);

        // --- SwitchTask: route based on needs_normalize ---
        String normalizeSwitchRef = agentName + "_guardrail_normalize_switch" + s;
        WorkflowTask normalizeSwitch = new WorkflowTask();
        normalizeSwitch.setType("SWITCH");
        normalizeSwitch.setTaskReferenceName(normalizeSwitchRef);
        normalizeSwitch.setEvaluatorType("graaljs");
        normalizeSwitch.setExpression(
                "$.needs_normalize == true ? 'needs_normalize' : 'skip'");

        Map<String, Object> normalizeSwitchInputs = new LinkedHashMap<>();
        normalizeSwitchInputs.put("needs_normalize",
                "${" + validateRef + ".output.result.needs_normalize}");
        normalizeSwitch.setInputParameters(normalizeSwitchInputs);

        Map<String, List<WorkflowTask>> normalizeCases = new LinkedHashMap<>();

        // "needs_normalize" case: LlmChatComplete normalizer
        String normalizerRef = agentName + "_guardrail_normalizer" + s;

        // Use the agent's model (from guard config or fallback)
        // For the human case normalizer, we need a model. Use the guard's model if available,
        // otherwise this would need to be passed in. For now, we use a reasonable approach:
        // the guard config may not have a model for non-LLM guardrails, so we build the
        // normalizer task with input parameters that can be overridden.
        WorkflowTask normalizerTask = new WorkflowTask();
        normalizerTask.setName("LLM_CHAT_COMPLETE");
        normalizerTask.setTaskReferenceName(normalizerRef);
        normalizerTask.setType("LLM_CHAT_COMPLETE");

        String normalizerSystemPrompt = "Convert the human's response into a JSON object:\n"
                + "{\"approved\": <boolean>, \"edited_output\": <string or null>, \"reason\": <string or null>}\n\n"
                + "Rules:\n"
                + "- approved=true for: approve, yes, ok, LGTM, looks good, go ahead, etc.\n"
                + "- approved=false for: reject, no, deny, not approved, etc.\n"
                + "- If they provide corrected content, put it in edited_output.\n"
                + "- If they give a reason for rejection, put it in reason.\n"
                + "- If input is already valid JSON with these fields, return as-is.\n"
                + "Output ONLY the JSON object.";

        Map<String, Object> normalizerInputs = new LinkedHashMap<>();
        // Use guard's model if available, otherwise fall back to agent's model
        String modelToUse = guard.getModel() != null ? guard.getModel() : agentModel;
        if (modelToUse != null) {
            ModelParser.ParsedModel parsed = ModelParser.parse(modelToUse);
            normalizerInputs.put("llmProvider", parsed.getProvider());
            normalizerInputs.put("model", parsed.getModel());
        }
        normalizerInputs.put("messages", List.of(
                Map.of("role", "system", "message", normalizerSystemPrompt),
                Map.of("role", "user", "message",
                        "${" + validateRef + ".output.result.raw_text}")
        ));
        normalizerInputs.put("temperature", 0);
        normalizerInputs.put("jsonOutput", true);
        normalizerTask.setInputParameters(normalizerInputs);

        normalizeCases.put("needs_normalize", List.of(normalizerTask));

        // default (skip): no-op
        WorkflowTask normalizeNoop = new WorkflowTask();
        normalizeNoop.setType("SET_VARIABLE");
        normalizeNoop.setTaskReferenceName(agentName + "_guardrail_normalize_noop" + s);

        Map<String, Object> normalizeNoopInputs = new LinkedHashMap<>();
        normalizeNoopInputs.put("_normalize_skipped", true);
        normalizeNoop.setInputParameters(normalizeNoopInputs);

        normalizeSwitch.setDecisionCases(normalizeCases);
        normalizeSwitch.setDefaultCase(List.of(normalizeNoop));
        humanCaseTasks.add(normalizeSwitch);

        // --- Process InlineTask: merge validated/normalized ---
        String humanProcessRef = agentName + "_guardrail_human_process" + s;
        WorkflowTask humanProcessTask = new WorkflowTask();
        humanProcessTask.setTaskReferenceName(humanProcessRef);
        humanProcessTask.setType("INLINE");

        Map<String, Object> processInputs = new LinkedHashMap<>();
        processInputs.put("evaluatorType", "graaljs");
        processInputs.put("expression", JavaScriptBuilder.humanProcessScript());
        processInputs.put("validated", "${" + validateRef + ".output.result}");
        processInputs.put("normalized", "${" + normalizerRef + ".output.result}");
        processInputs.put("llm_output", contentRef);
        humanProcessTask.setInputParameters(processInputs);
        humanCaseTasks.add(humanProcessTask);

        // --- Inner SwitchTask: approve/edit/reject ---
        WorkflowTask innerSwitch = new WorkflowTask();
        innerSwitch.setType("SWITCH");
        innerSwitch.setTaskReferenceName(agentName + "_guardrail_human_action" + s);
        innerSwitch.setEvaluatorType("value-param");
        innerSwitch.setExpression("switchCaseValue");

        Map<String, Object> innerSwitchInputs = new LinkedHashMap<>();
        innerSwitchInputs.put("switchCaseValue",
                "${" + humanProcessRef + ".output.result.action}");
        innerSwitch.setInputParameters(innerSwitchInputs);

        Map<String, List<WorkflowTask>> innerCases = new LinkedHashMap<>();

        // "approve" case: no-op, continue with original output
        WorkflowTask approveNoop = new WorkflowTask();
        approveNoop.setType("SET_VARIABLE");
        approveNoop.setTaskReferenceName(agentName + "_guardrail_human_approve" + s);

        Map<String, Object> approveInputs = new LinkedHashMap<>();
        approveInputs.put("_human_approved", true);
        approveNoop.setInputParameters(approveInputs);

        innerCases.put("approve", List.of(approveNoop));

        // "edit" case: pass through edited content
        WorkflowTask editNoop = new WorkflowTask();
        editNoop.setType("SET_VARIABLE");
        editNoop.setTaskReferenceName(agentName + "_guardrail_human_edit" + s);

        Map<String, Object> editInputs = new LinkedHashMap<>();
        editInputs.put("_human_edited_output",
                "${" + humanProcessRef + ".output.result.result}");
        editNoop.setInputParameters(editInputs);

        innerCases.put("edit", List.of(editNoop));

        innerSwitch.setDecisionCases(innerCases);

        // reject (default): terminate
        WorkflowTask rejectTerminate = new WorkflowTask();
        rejectTerminate.setType("TERMINATE");
        rejectTerminate.setTaskReferenceName(agentName + "_guardrail_human_reject" + s);

        Map<String, Object> rejectInputs = new LinkedHashMap<>();
        rejectInputs.put("terminationStatus", "FAILED");
        rejectInputs.put("terminationReason",
                "${" + humanProcessRef + ".output.result.reason}");
        rejectTerminate.setInputParameters(rejectInputs);

        innerSwitch.setDefaultCase(List.of(rejectTerminate));
        humanCaseTasks.add(innerSwitch);

        return humanCaseTasks;
    }
}
