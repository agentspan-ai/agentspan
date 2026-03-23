/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;

/**
 * Helper for building JavaScript snippets for Conductor InlineTask scripts.
 * All scripts are wrapped in IIFEs: (function() { ... })()
 */
public class JavaScriptBuilder {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    /**
     * Convert a Java object to a JSON string suitable for embedding in JavaScript.
     */
    public static String toJson(Object value) {
        try {
            return MAPPER.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new RuntimeException("Failed to serialize to JSON", e);
        }
    }

    /**
     * Wrap a script body in an IIFE.
     */
    public static String iife(String body) {
        return "(function() {" + body + "})()";
    }

    /**
     * Build the regex guardrail JavaScript.
     */
    public static String regexGuardrailScript(
            String patternsJson, String mode, String onFail,
            String message, int maxRetries, String guardrailName) {
        String messageJs = toJson(message);
        String nameJs = toJson(guardrailName);

        return iife(
            "  var content = $.content;" +
            "  var iteration = $.iteration;" +
            "  var patterns = " + patternsJson + ";" +
            "  var mode = " + toJson(mode) + ";" +
            "  var on_fail = " + toJson(onFail) + ";" +
            "  var message = " + messageJs + ";" +
            "  var max_retries = " + maxRetries + ";" +
            "  var guardrail_name = " + nameJs + ";" +
            "  var matched = false;" +
            "  for (var i = 0; i < patterns.length; i++) {" +
            "    if (new RegExp(patterns[i]).test(content)) { matched = true; break; }" +
            "  }" +
            "  var failed = (mode === 'block' && matched) || (mode === 'allow' && !matched);" +
            "  if (!failed) {" +
            "    return {passed: true, message: '', on_fail: 'pass'," +
            "            fixed_output: null, guardrail_name: '', should_continue: false};" +
            "  }" +
            "  var actual_fail = on_fail;" +
            "  if (on_fail === 'retry' && iteration >= max_retries) actual_fail = 'raise';" +
            "  if (on_fail === 'fix') actual_fail = 'raise';" +
            "  return {passed: false, message: message, on_fail: actual_fail," +
            "          fixed_output: null, guardrail_name: guardrail_name," +
            "          should_continue: actual_fail === 'retry'};"
        );
    }

    /**
     * Build the LLM guardrail parser JavaScript.
     */
    public static String llmGuardrailParserScript(String onFail, int maxRetries, String guardrailName) {
        return iife(
            "  var raw = $.llm_result;" +
            "  var iteration = $.iteration;" +
            "  var on_fail_mode = " + toJson(onFail) + ";" +
            "  var max_retries = " + maxRetries + ";" +
            "  var guardrail_name = " + toJson(guardrailName) + ";" +
            "  var data;" +
            "  try { data = typeof raw === 'string' ? JSON.parse(raw) : raw; }" +
            "  catch(e) { data = {passed: false, reason: 'Unparseable LLM response'}; }" +
            "  if (!!data.passed) {" +
            "    return {passed: true, message: '', on_fail: 'pass'," +
            "            fixed_output: null, guardrail_name: '', should_continue: false};" +
            "  }" +
            "  var actual_fail = on_fail_mode;" +
            "  if (on_fail_mode === 'retry' && iteration >= max_retries) actual_fail = 'raise';" +
            "  if (on_fail_mode === 'fix') actual_fail = 'raise';" +
            "  return {passed: false, message: data.reason || data.message || 'LLM guardrail failed'," +
            "          on_fail: actual_fail, fixed_output: null," +
            "          guardrail_name: guardrail_name, should_continue: actual_fail === 'retry'};"
        );
    }

    /**
     * Build JavaScript that formats tool call inputs into a readable string for guardrail evaluation.
     *
     * <p>Input: {@code $.tool_calls} — array of {@code {name, input}} objects.
     * Output: {@code {formatted: "Tool: name\nArguments: {...}\n---\n...", count: N}}
     */
    public static String formatToolCallsScript() {
        return iife(
            "  var tcs = $.tool_calls || [];" +
            "  var lines = [];" +
            "  for (var i = 0; i < tcs.length; i++) {" +
            "    var tc = tcs[i];" +
            "    var args = tc.inputParameters || tc.input || {};" +
            "    var cleaned = {};" +
            "    for (var k in args) { if (k !== 'method') cleaned[k] = args[k]; }" +
            "    lines.push('Tool: ' + tc.name);" +
            "    lines.push('Arguments: ' + JSON.stringify(cleaned));" +
            "    lines.push('---');" +
            "  }" +
            "  return {formatted: lines.join('\\n'), count: tcs.length};"
        );
    }

    /**
     * Build the guardrail retry feedback JavaScript.
     */
    public static String guardrailRetryScript() {
        return iife(
            "  return {result: '[Output validation failed: '" +
            "    + $.guardrail_message" +
            "    + '. Please revise your response.]'};"
        );
    }

    /**
     * Build the guardrail fix pass-through JavaScript.
     */
    public static String guardrailFixScript() {
        return "(function() { return {result: $.fixed_output}; })()";
    }

    /**
     * Build the output resolution JavaScript.
     * Checks if a guardrail fix or human edit stored a replacement output
     * in workflow variables, and uses it instead of the raw LLM output.
     */
    public static String resolveOutputScript() {
        return iife(
            "  var fixed = $.fixed_output;" +
            "  var edited = $.edited_output;" +
            "  if (edited != null && edited !== '' && edited !== 'null') {" +
            "    return {result: edited, finishReason: 'STOP'};" +
            "  } else if (fixed != null && fixed !== '' && fixed !== 'null') {" +
            "    return {result: fixed, finishReason: 'STOP'};" +
            "  } else {" +
            "    return {result: $.llm_result, finishReason: $.finish_reason};" +
            "  }"
        );
    }

    /**
     * Build the tool call enrichment JavaScript.
     * Injects {@code _agent_state} from {@code $.agentState} into worker (SIMPLE) tasks
     * so that ToolContext.state is available server-side.
     * Injects {@code _allowed_commands} for CLI (SIMPLE) tasks so that per-agent
     * command whitelists are enforced even when multiple agents share the same worker.
     */
    public static String enrichToolsScript(String httpConfigJson, String mcpConfigJson,
                                              String mediaConfigJson, String agentToolConfigJson,
                                              String ragConfigJson, String cliConfigJson,
                                              String humanConfigJson) {
        return iife(
            "  var httpCfg = " + httpConfigJson + ";" +
            "  var mcpCfg = " + mcpConfigJson + ";" +
            "  var mediaCfg = " + mediaConfigJson + ";" +
            "  var agentToolCfg = " + agentToolConfigJson + ";" +
            "  var ragCfg = " + ragConfigJson + ";" +
            "  var cliCfg = " + cliConfigJson + ";" +
            "  var humanCfg = " + humanConfigJson + ";" +
            "  var agentState = $.agentState || {};" +
            "  var tcs = $.toolCalls || [];" +
            "  var result = [];" +
            "  for (var i = 0; i < tcs.length; i++) {" +
            "    var tc = tcs[i]; var n = tc.name;" +
            "    var t = {name: n, taskReferenceName: tc.taskReferenceName || n," +
            "             type: tc.type || 'SIMPLE', inputParameters: tc.inputParameters || {}," +
            "             optional: true," +
            "             retryCount: 2, retryLogic: 'LINEAR_BACKOFF'," +
            "             retryDelaySeconds: 2};" +
            "    if (httpCfg[n]) {" +
            "      t.type = 'HTTP';" +
            "      t.inputParameters = {http_request: {" +
            "        uri: httpCfg[n].url || ''," +
            "        method: httpCfg[n].method || 'GET'," +
            "        headers: httpCfg[n].headers || {}," +
            "        body: tc.inputParameters || {}," +
            "        accept: httpCfg[n].accept || 'application/json'," +
            "        contentType: httpCfg[n].contentType || 'application/json'," +
            "        connectionTimeOut: 30000," +
            "        readTimeOut: 30000}};" +
            "      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
            "    } else if (mcpCfg[n]) {" +
            "      t.type = 'CALL_MCP_TOOL';" +
            "      t.name = 'call_mcp_tool';" +
            "      t.inputParameters = {" +
            "        mcpServer: mcpCfg[n].mcpServer || ''," +
            "        method: n," +
            "        arguments: tc.inputParameters || {}," +
            "        headers: mcpCfg[n].headers || {}};" +
            "      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
            "    } else if (agentToolCfg[n]) {" +
            "      t.type = 'SUB_WORKFLOW';" +
            "      t.name = agentToolCfg[n].workflowName;" +
            "      t.subWorkflowParam = {name: agentToolCfg[n].workflowName, version: 1};" +
            "      t.inputParameters = {" +
            "        prompt: (tc.inputParameters && tc.inputParameters.request)" +
            "                || JSON.stringify(tc.inputParameters)," +
            "        session_id: $.session_id || ''};" +
            "      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
            "      if (agentToolCfg[n].retryCount !== undefined) t.retryCount = agentToolCfg[n].retryCount;" +
            "      if (agentToolCfg[n].retryDelaySeconds !== undefined) t.retryDelaySeconds = agentToolCfg[n].retryDelaySeconds;" +
            "      if (agentToolCfg[n].optional !== undefined) t.optional = agentToolCfg[n].optional;" +
            "    } else if (mediaCfg[n]) {" +
            "      t.type = mediaCfg[n].taskType;" +
            "      t.name = mediaCfg[n].taskType.toLowerCase();" +
            "      var merged = {};" +
            "      var defs = mediaCfg[n].defaults || {};" +
            "      for (var k in defs) { merged[k] = defs[k]; }" +
            "      var inp = tc.inputParameters || {};" +
            "      for (var k in inp) { merged[k] = inp[k]; }" +
            "      t.inputParameters = merged;" +
            "    } else if (ragCfg[n]) {" +
            "      t.type = ragCfg[n].taskType;" +
            "      t.name = ragCfg[n].taskType.toLowerCase();" +
            "      var merged = {};" +
            "      var defs = ragCfg[n].defaults || {};" +
            "      for (var k in defs) { merged[k] = defs[k]; }" +
            "      var inp = tc.inputParameters || {};" +
            "      for (var k in inp) { merged[k] = inp[k]; }" +
            "      t.inputParameters = merged;" +
            "    } else if (humanCfg[n]) {" +
            "      t.type = 'HUMAN';" +
            "      t.name = n;" +
            "      var hDef = {assignmentCompletionStrategy: 'LEAVE_OPEN'," +
            "                  displayName: humanCfg[n].displayName || n," +
            "                  userFormTemplate: {version: 0}};" +
            "      var hInputs = {__humanTaskDefinition: hDef};" +
            "      hInputs.response_schema = {type: 'object', properties: {" +
            "        response: {type: 'string', title: 'Response'," +
            "                   description: 'Provide your response'}}};" +
            "      hInputs.response_ui_schema = {'ui:order': ['response']," +
            "        response: {'ui:widget': 'textarea'}};" +
            "      var inp = tc.inputParameters || {};" +
            "      for (var k in inp) { hInputs[k] = inp[k]; }" +
            "      if (humanCfg[n].description) hInputs._description = humanCfg[n].description;" +
            "      t.inputParameters = hInputs;" +
            "      t.optional = false;" +
            "    }" +
            "    if (t.type === 'SIMPLE') {" +
            "      t.inputParameters._agent_state = agentState;" +
            "      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
            "      if (cliCfg[n]) { t.inputParameters._allowed_commands = cliCfg[n].allowedCommands; }" +
            "    }" +
            "    result.push(t);" +
            "  }" +
            "  return {dynamicTasks: result};"
        );
    }

    /**
     * Build tool filter inline script.
     */
    public static String filterToolsScript(String allSpecsJson) {
        return iife(
            "  var allTools = " + allSpecsJson + ";" +
            "  var raw = $.selectedNames || '[]';" +
            "  var selected;" +
            "  try { selected = typeof raw === 'string' ? JSON.parse(raw) : raw; }" +
            "  catch(e) { selected = []; }" +
            "  if (!Array.isArray(selected)) {" +
            "    if (selected && selected.selected_tools) selected = selected.selected_tools;" +
            "    else selected = [];" +
            "  }" +
            "  var nameSet = {};" +
            "  for (var i = 0; i < selected.length; i++) nameSet[selected[i]] = true;" +
            "  var result = [];" +
            "  for (var i = 0; i < allTools.length; i++) {" +
            "    if (nameSet[allTools[i].name]) result.push(allTools[i]);" +
            "  }" +
            "  if (result.length === 0) result = allTools;" +
            "  return {tools: result};"
        );
    }

    /**
     * Build round-robin select script (simple: iteration % N).
     */
    public static String roundRobinSelectScript(int numAgents) {
        return "(function() { return String($.iteration % " + numAgents + "); })()";
    }

    /**
     * Build random select script (simple: random * N).
     */
    public static String randomSelectScript(int numAgents) {
        return "(function() { return String(Math.floor(Math.random() * " + numAgents + ")); })()";
    }

    /**
     * Build constrained round-robin select script with allowed transitions.
     */
    public static String constrainedRoundRobinScript(String idxMapJson, int numAgents) {
        return iife(
            "  var allowed = " + idxMapJson + ";" +
            "  var last = String($.last_agent);" +
            "  var candidates = allowed[last];" +
            "  if (!candidates) candidates = Array.from(Array(" + numAgents + ").keys());" +
            "  var idx = $.iteration % candidates.length;" +
            "  return String(candidates[idx]);"
        );
    }

    /**
     * Build constrained random select script with allowed transitions.
     */
    public static String constrainedRandomScript(String idxMapJson, int numAgents) {
        return iife(
            "  var allowed = " + idxMapJson + ";" +
            "  var last = String($.last_agent);" +
            "  var candidates = allowed[last];" +
            "  if (!candidates) candidates = Array.from(Array(" + numAgents + ").keys());" +
            "  var pick = candidates[Math.floor(Math.random() * candidates.length)];" +
            "  return String(pick);"
        );
    }

    /**
     * Build concat script for multi-agent transcript accumulation.
     */
    public static String concatScript(String agentName) {
        return "(function() { var r = $.response; " +
            "r = (r == null || r === undefined) ? '' : (typeof r === 'object' ? JSON.stringify(r) : String(r)); " +
            "return $.prev + '\\n\\n[" + agentName + "]: ' + r; })()";
    }

    /**
     * Build human task validation script for guardrails.
     */
    public static String humanValidateScript() {
        return iife(
            "  var raw = $.human_output;" +
            "  if (!raw) return {needs_normalize: true, raw_text: ''};" +
            "  var raw_text;" +
            "  if (typeof raw === 'string') { raw_text = raw; }" +
            "  else if (typeof raw.result === 'string') { raw_text = raw.result; }" +
            "  else { var p = []; for (var k in raw) { p.push(k + ': ' + raw[k]); }" +
            "         raw_text = p.join(', '); }" +
            "  if (typeof raw === 'object' && typeof raw.approved === 'boolean') {" +
            "    return {" +
            "      needs_normalize: false," +
            "      approved: raw.approved," +
            "      edited_output: raw.edited_output || null," +
            "      reason: raw.reason || null," +
            "      raw_text: raw_text" +
            "    };" +
            "  }" +
            "  if (typeof raw === 'object' && typeof raw.approved === 'string') {" +
            "    var a = raw.approved.toLowerCase().trim();" +
            "    if (a === 'true' || a === 'yes' || a === 'y') {" +
            "      return {needs_normalize: false, approved: true," +
            "              edited_output: raw.edited_output || null, reason: raw.reason || null," +
            "              raw_text: raw_text};" +
            "    }" +
            "    if (a === 'false' || a === 'no' || a === 'n') {" +
            "      return {needs_normalize: false, approved: false," +
            "              edited_output: null, reason: raw.reason || null," +
            "              raw_text: raw_text};" +
            "    }" +
            "  }" +
            "  return {needs_normalize: true, raw_text: raw_text};"
        );
    }

    /**
     * Build human process script for guardrail decision merging.
     */
    public static String humanProcessScript() {
        return iife(
            "  var validated = $.validated;" +
            "  var normalized = $.normalized;" +
            "  var data = (validated && !validated.needs_normalize) ? validated : (normalized || {});" +
            "  if (data.approved) {" +
            "    return {action: 'approve', result: $.llm_output};" +
            "  } else if (data.edited_output) {" +
            "    return {action: 'edit', result: data.edited_output};" +
            "  } else {" +
            "    var reason = data.reason || 'Rejected by human reviewer';" +
            "    return {action: 'reject', reason: reason};" +
            "  }"
        );
    }

    /**
     * Build approval validate script for tool approval flow.
     * Like humanValidateScript but without edited_output field.
     */
    public static String approvalValidateScript() {
        return iife(
            "  var raw = $.human_output;" +
            "  if (!raw) return {needs_normalize: true, raw_text: '', extra: {}};" +
            "  var raw_text;" +
            "  if (typeof raw === 'string') { raw_text = raw; }" +
            "  else if (typeof raw.result === 'string') { raw_text = raw.result; }" +
            "  else { var p = []; for (var k in raw) { p.push(k + ': ' + raw[k]); }" +
            "         raw_text = p.join(', '); }" +
            // Collect extra fields (everything except approved/reason)
            "  var extra = {};" +
            "  if (typeof raw === 'object') {" +
            "    for (var k in raw) {" +
            "      if (k !== 'approved' && k !== 'reason') { extra[k] = raw[k]; }" +
            "    }" +
            "  }" +
            "  if (typeof raw === 'object' && typeof raw.approved === 'boolean') {" +
            "    return {needs_normalize: false, approved: raw.approved," +
            "            reason: raw.reason || null, raw_text: raw_text, extra: extra};" +
            "  }" +
            "  if (typeof raw === 'object' && typeof raw.approved === 'string') {" +
            "    var a = raw.approved.toLowerCase().trim();" +
            "    if (a === 'true' || a === 'yes' || a === 'y') {" +
            "      return {needs_normalize: false, approved: true, reason: raw.reason || null," +
            "              raw_text: raw_text, extra: extra};" +
            "    }" +
            "    if (a === 'false' || a === 'no' || a === 'n') {" +
            "      return {needs_normalize: false, approved: false, reason: raw.reason || null," +
            "              raw_text: raw_text, extra: extra};" +
            "    }" +
            "  }" +
            "  return {needs_normalize: true, raw_text: raw_text, extra: extra};"
        );
    }

    /**
     * Build the MCP prepare/merge script that combines static tool specs with
     * dynamically discovered MCP tools from LIST_MCP_TOOLS tasks.
     *
     * <p>At runtime this script:</p>
     * <ol>
     *   <li>Parses static (non-MCP) tool specs from a baked-in JSON literal</li>
     *   <li>Reads discovered tools from each LIST_MCP_TOOLS task output</li>
     *   <li>Converts each discovered tool into a tool spec with {@code type: "CALL_MCP_TOOL"}</li>
     *   <li>Builds an {@code mcpConfig} map (tool name → server URL + headers)</li>
     *   <li>Checks whether total tool count exceeds the threshold</li>
     * </ol>
     *
     * @param staticSpecsJson JSON array of static tool specs (baked in at compile time)
     * @param serverCount     number of MCP servers (each provides $.discovered_N input)
     * @param serversJson     JSON array of [{serverUrl, headers}, ...] for each server
     * @param maxTools        threshold for filtering
     */
    public static String mcpPrepareScript(String staticSpecsJson, int serverCount,
                                          String serversJson, int maxTools) {
        StringBuilder discoveredReads = new StringBuilder();
        for (int i = 0; i < serverCount; i++) {
            discoveredReads.append("  var d").append(i).append(" = $.discovered_").append(i).append(" || [];");
        }
        StringBuilder mergeLoop = new StringBuilder();
        for (int i = 0; i < serverCount; i++) {
            mergeLoop.append(
                "  for (var i = 0; i < d" + i + ".length; i++) {" +
                "    var t = d" + i + "[i];" +
                "    var s = servers[" + i + "];" +
                "    specs.push({name: t.name, type: 'CALL_MCP_TOOL'," +
                "      description: t.description || ''," +
                "      inputSchema: t.inputSchema || {type:'object',properties:{}}," +
                "      configParams: {mcpServer: s.serverUrl, headers: s.headers || {}}});" +
                "    mcpCfg[t.name] = {mcpServer: s.serverUrl, headers: s.headers || {}};" +
                "  }");
        }

        return iife(
            "  var specs = " + staticSpecsJson + ";" +
            "  var servers = " + serversJson + ";" +
            "  var mcpCfg = {};" +
            discoveredReads +
            mergeLoop +
            "  return {tools: specs, mcpConfig: mcpCfg," +
            "    needsFilter: specs.length > " + maxTools + "};"
        );
    }

    /**
     * Build tool enrichment script with dynamic MCP config from runtime input.
     *
     * <p>Like {@link #enrichToolsScript} but reads {@code mcpCfg} from {@code $.mcpConfig}
     * (runtime input from the prepare task) instead of a baked-in JSON literal.
     * HTTP and media configs are still baked in since they're known at compile time.</p>
     */
    public static String enrichToolsScriptDynamic(String httpConfigJson, String mediaConfigJson,
                                                     String agentToolConfigJson, String ragConfigJson,
                                                     String humanConfigJson) {
        return iife(
            "  var httpCfg = " + httpConfigJson + ";" +
            "  var mcpCfg = $.mcpConfig || {};" +
            "  var mediaCfg = " + mediaConfigJson + ";" +
            "  var agentToolCfg = " + agentToolConfigJson + ";" +
            "  var ragCfg = " + ragConfigJson + ";" +
            "  var humanCfg = " + humanConfigJson + ";" +
            "  var agentState = $.agentState || {};" +
            "  var tcs = $.toolCalls || [];" +
            "  var result = [];" +
            "  for (var i = 0; i < tcs.length; i++) {" +
            "    var tc = tcs[i]; var n = tc.name;" +
            "    var t = {name: n, taskReferenceName: tc.taskReferenceName || n," +
            "             type: tc.type || 'SIMPLE', inputParameters: tc.inputParameters || {}," +
            "             optional: true," +
            "             retryCount: 2, retryLogic: 'LINEAR_BACKOFF'," +
            "             retryDelaySeconds: 2};" +
            "    if (httpCfg[n]) {" +
            "      t.type = 'HTTP';" +
            "      t.inputParameters = {http_request: {" +
            "        uri: httpCfg[n].url || ''," +
            "        method: httpCfg[n].method || 'GET'," +
            "        headers: httpCfg[n].headers || {}," +
            "        body: tc.inputParameters || {}," +
            "        accept: httpCfg[n].accept || 'application/json'," +
            "        contentType: httpCfg[n].contentType || 'application/json'," +
            "        connectionTimeOut: 30000," +
            "        readTimeOut: 30000}};" +
            "      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
            "    } else if (mcpCfg[n]) {" +
            "      t.type = 'CALL_MCP_TOOL';" +
            "      t.name = 'call_mcp_tool';" +
            "      t.inputParameters = {" +
            "        mcpServer: mcpCfg[n].mcpServer || ''," +
            "        method: n," +
            "        arguments: tc.inputParameters || {}," +
            "        headers: mcpCfg[n].headers || {}};" +
            "      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
            "    } else if (agentToolCfg[n]) {" +
            "      t.type = 'SUB_WORKFLOW';" +
            "      t.name = agentToolCfg[n].workflowName;" +
            "      t.subWorkflowParam = {name: agentToolCfg[n].workflowName, version: 1};" +
            "      t.inputParameters = {" +
            "        prompt: (tc.inputParameters && tc.inputParameters.request)" +
            "                || JSON.stringify(tc.inputParameters)," +
            "        session_id: $.session_id || ''};" +
            "      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
            "      if (agentToolCfg[n].retryCount !== undefined) t.retryCount = agentToolCfg[n].retryCount;" +
            "      if (agentToolCfg[n].retryDelaySeconds !== undefined) t.retryDelaySeconds = agentToolCfg[n].retryDelaySeconds;" +
            "      if (agentToolCfg[n].optional !== undefined) t.optional = agentToolCfg[n].optional;" +
            "    } else if (mediaCfg[n]) {" +
            "      t.type = mediaCfg[n].taskType;" +
            "      t.name = mediaCfg[n].taskType.toLowerCase();" +
            "      var merged = {};" +
            "      var defs = mediaCfg[n].defaults || {};" +
            "      for (var k in defs) { merged[k] = defs[k]; }" +
            "      var inp = tc.inputParameters || {};" +
            "      for (var k in inp) { merged[k] = inp[k]; }" +
            "      t.inputParameters = merged;" +
            "    } else if (ragCfg[n]) {" +
            "      t.type = ragCfg[n].taskType;" +
            "      t.name = ragCfg[n].taskType.toLowerCase();" +
            "      var merged = {};" +
            "      var defs = ragCfg[n].defaults || {};" +
            "      for (var k in defs) { merged[k] = defs[k]; }" +
            "      var inp = tc.inputParameters || {};" +
            "      for (var k in inp) { merged[k] = inp[k]; }" +
            "      t.inputParameters = merged;" +
            "    } else if (humanCfg[n]) {" +
            "      t.type = 'HUMAN';" +
            "      t.name = n;" +
            "      var hDef = {assignmentCompletionStrategy: 'LEAVE_OPEN'," +
            "                  displayName: humanCfg[n].displayName || n," +
            "                  userFormTemplate: {version: 0}};" +
            "      var hInputs = {__humanTaskDefinition: hDef};" +
            "      hInputs.response_schema = {type: 'object', properties: {" +
            "        response: {type: 'string', title: 'Response'," +
            "                   description: 'Provide your response'}}};" +
            "      hInputs.response_ui_schema = {'ui:order': ['response']," +
            "        response: {'ui:widget': 'textarea'}};" +
            "      var inp = tc.inputParameters || {};" +
            "      for (var k in inp) { hInputs[k] = inp[k]; }" +
            "      if (humanCfg[n].description) hInputs._description = humanCfg[n].description;" +
            "      t.inputParameters = hInputs;" +
            "      t.optional = false;" +
            "    }" +
            "    if (t.type === 'SIMPLE') {" +
            "      t.inputParameters._agent_state = agentState;" +
            "      if ($.agentspanCtx) { t.inputParameters.__agentspan_ctx__ = $.agentspanCtx; }" +
            "    }" +
            "    result.push(t);" +
            "  }" +
            "  return {dynamicTasks: result};"
        );
    }

    /**
     * Build tool filter script that reads the tool list from a runtime input
     * instead of a baked-in JSON literal.
     */
    public static String filterToolsScriptDynamic() {
        return iife(
            "  var allTools = $.allTools || [];" +
            "  var raw = $.selectedNames || '[]';" +
            "  var selected;" +
            "  try { selected = typeof raw === 'string' ? JSON.parse(raw) : raw; }" +
            "  catch(e) { selected = []; }" +
            "  if (!Array.isArray(selected)) {" +
            "    if (selected && selected.selected_tools) selected = selected.selected_tools;" +
            "    else selected = [];" +
            "  }" +
            "  var nameSet = {};" +
            "  for (var i = 0; i < selected.length; i++) nameSet[selected[i]] = true;" +
            "  var result = [];" +
            "  for (var i = 0; i < allTools.length; i++) {" +
            "    if (nameSet[allTools[i].name]) result.push(allTools[i]);" +
            "  }" +
            "  if (result.length === 0) result = allTools;" +
            "  return {tools: result};"
        );
    }

    /**
     * Build the MCP resolve script that picks the final tools and mcpConfig
     * from either the filter output or the prepare output, depending on
     * which path was taken in the threshold SWITCH.
     */
    public static String mcpResolveScript() {
        return iife(
            "  var filtered = $.filtered_tools;" +
            "  var prepared = $.prepared_tools;" +
            "  var mcpConfig = $.mcpConfig;" +
            "  var tools = (filtered && filtered.length > 0) ? filtered : prepared;" +
            "  return {tools: tools, mcpConfig: mcpConfig};"
        );
    }

    /**
     * Build the catalog text inline script for dynamic tool filtering.
     * Builds the LLM prompt catalog from the runtime tools list.
     */
    public static String filterCatalogScript(int maxTools) {
        return iife(
            "  var tools = $.tools || [];" +
            "  var lines = [];" +
            "  for (var i = 0; i < tools.length; i++) {" +
            "    lines.push('- ' + tools[i].name + ': ' + (tools[i].description || ''));" +
            "  }" +
            "  return {catalog: lines.join('\\n'), maxTools: " + maxTools + "};"
        );
    }

    /**
     * Format custom data from a human approval response into a readable
     * system message for the LLM. Returns an empty string if no extra data.
     */
    public static String formatHumanFeedbackScript() {
        return iife(
            "  var extra = $.extra || {};" +
            "  var reason = $.reason || '';" +
            "  var parts = [];" +
            "  for (var k in extra) { parts.push(k + ': ' + JSON.stringify(extra[k])); }" +
            "  if (parts.length === 0 && !reason) return '';" +
            "  var msg = 'Human reviewer feedback:';" +
            "  if (reason) msg += ' Reason: ' + reason + '.';" +
            "  if (parts.length > 0) msg += ' Additional context: ' + parts.join(', ') + '.';" +
            "  return msg;"
        );
    }

    /**
     * Validate human output for graph-node HUMAN tasks.
     *
     * <p>Extracts key-value fields from the human output. If the output is already
     * a structured JSON object, captures all fields (except internal ones like
     * {@code __humanTaskDefinition}). If it's a string, flags for LLM normalization.
     */
    public static String graphNodeValidateScript() {
        return iife(
            "  var raw = $.human_output;" +
            "  if (!raw) return {needs_normalize: true, raw_text: '', fields: {}};" +
            "  var raw_text;" +
            "  if (typeof raw === 'string') { raw_text = raw; }" +
            "  else if (typeof raw.result === 'string') { raw_text = raw.result; }" +
            "  else { var p = []; for (var k in raw) { if (k !== '__humanTaskDefinition' && k !== 'response_schema'" +
            "      && k !== 'response_ui_schema' && k !== '_prompt' && k !== 'state')" +
            "      p.push(k + ': ' + JSON.stringify(raw[k])); }" +
            "    raw_text = p.join(', '); }" +
            // Check if raw is a structured object with user-provided fields
            "  if (typeof raw === 'object') {" +
            "    var fields = {}; var hasFields = false;" +
            "    for (var k in raw) {" +
            "      if (k === '__humanTaskDefinition' || k === 'response_schema'" +
            "          || k === 'response_ui_schema' || k === '_prompt' || k === 'state') continue;" +
            "      fields[k] = raw[k]; hasFields = true;" +
            "    }" +
            "    if (hasFields) {" +
            "      return {needs_normalize: false, fields: fields, raw_text: raw_text};" +
            "    }" +
            "  }" +
            "  return {needs_normalize: true, raw_text: raw_text, fields: {}};"
        );
    }

    /**
     * Merge validated/normalized human output into graph state.
     *
     * <p>Takes the validated fields (or LLM-normalized JSON), merges them
     * into the previous graph state, and returns the updated state.
     */
    public static String graphNodeProcessScript() {
        return iife(
            "  var validated = $.validated;" +
            "  var normalized = $.normalized;" +
            "  var state = $.previousState || {};" +
            "  var fields;" +
            "  if (validated && !validated.needs_normalize) {" +
            "    fields = validated.fields || {};" +
            "  } else if (normalized) {" +
            // normalized is LLM output — parse if string
            "    if (typeof normalized === 'string') {" +
            "      try { fields = JSON.parse(normalized); } catch(e) { fields = {}; }" +
            "    } else { fields = normalized; }" +
            "  } else { fields = {}; }" +
            // Merge fields into state
            "  for (var k in fields) {" +
            "    if (k !== '__humanTaskDefinition') state[k] = fields[k];" +
            "  }" +
            "  return {state: state, result: JSON.stringify(state)};"
        );
    }

    /**
     * Build approval check script for tool approval flow.
     */
    public static String approvalCheckScript() {
        return iife(
            "  var validated = $.validated;" +
            "  var normalized = $.normalized;" +
            "  var data = (validated && !validated.needs_normalize) ? validated : (normalized || {});" +
            "  var extra = (validated && validated.extra) ? validated.extra : {};" +
            "  return {approved: data.approved === true, reason: data.reason || '', extra: extra};"
        );
    }

    /**
     * Build the state merge script that collects {@code _state_updates} from all
     * forked tool task outputs and merges them into a single state dict.
     *
     * <p>Reads {@code $.currentState} (the existing workflow variable) and
     * {@code $.joinOutput} (the JOIN task output containing all tool results).
     * Each tool may include {@code _state_updates} in its output; these are
     * shallow-merged onto the base state.</p>
     */
    public static String stateMergeScript() {
        return iife(
            "  var base = $.currentState || {};" +
            "  var joinOutput = $.joinOutput || {};" +
            "  for (var key in joinOutput) {" +
            "    var taskOut = joinOutput[key] || {};" +
            "    var updates = taskOut._state_updates;" +
            "    if (updates) {" +
            "      for (var k in updates) {" +
            "        var bv = base[k]; var uv = updates[k];" +
            "        if (Array.isArray(bv) && Array.isArray(uv)) {" +
            // Array merge: concat unique items from update that aren't in base
            "          for (var i = 0; i < uv.length; i++) {" +
            "            var found = false;" +
            "            for (var j = 0; j < bv.length; j++) {" +
            "              if (JSON.stringify(bv[j]) === JSON.stringify(uv[i])) { found = true; break; }" +
            "            }" +
            "            if (!found) bv.push(uv[i]);" +
            "          }" +
            "        } else { base[k] = uv; }" +
            "      }" +
            "    }" +
            "  }" +
            "  return {mergedState: base};"
        );
    }

    /**
     * Build a JavaScript snippet that checks whether all required tools have been called.
     * Scans the loop output for completed task reference names containing each required tool name.
     */
    public static String requiredToolsCheckScript(List<String> requiredTools) {
        StringBuilder sb = new StringBuilder();
        sb.append("(function() {");
        sb.append("  var required = ").append(toJson(requiredTools)).append(";");
        sb.append("  var output = $.completedTaskNames;");
        sb.append("  var outputStr = JSON.stringify(output);");
        sb.append("  var missing = [];");
        sb.append("  for (var i = 0; i < required.length; i++) {");
        sb.append("    if (outputStr.indexOf(required[i]) < 0) missing.push(required[i]);");
        sb.append("  }");
        sb.append("  if (missing.length > 0) {");
        sb.append("    return { satisfied: false, missing: missing,");
        sb.append("             message: 'You MUST call these tools before completing: ' + missing.join(', ') };");
        sb.append("  }");
        sb.append("  return { satisfied: true };");
        sb.append("})()");
        return sb.toString();
    }
}
