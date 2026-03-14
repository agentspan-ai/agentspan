/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

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
            "  var actual_fail = (on_fail === 'retry' && iteration >= max_retries) ? 'raise' : on_fail;" +
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
            "  var actual_fail = (on_fail_mode === 'retry' && iteration >= max_retries) ? 'raise' : on_fail_mode;" +
            "  return {passed: false, message: data.reason || data.message || 'LLM guardrail failed'," +
            "          on_fail: actual_fail, fixed_output: null," +
            "          guardrail_name: guardrail_name, should_continue: actual_fail === 'retry'};"
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
     * Build the tool call enrichment JavaScript.
     * Injects {@code _agent_state} from {@code $.agentState} into worker (SIMPLE) tasks
     * so that ToolContext.state is available server-side.
     */
    public static String enrichToolsScript(String httpConfigJson, String mcpConfigJson,
                                              String mediaConfigJson, String agentToolConfigJson,
                                              String ragConfigJson) {
        return iife(
            "  var httpCfg = " + httpConfigJson + ";" +
            "  var mcpCfg = " + mcpConfigJson + ";" +
            "  var mediaCfg = " + mediaConfigJson + ";" +
            "  var agentToolCfg = " + agentToolConfigJson + ";" +
            "  var ragCfg = " + ragConfigJson + ";" +
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
            "    } else if (mcpCfg[n]) {" +
            "      t.type = 'CALL_MCP_TOOL';" +
            "      t.name = 'call_mcp_tool';" +
            "      t.inputParameters = {" +
            "        mcpServer: mcpCfg[n].mcpServer || ''," +
            "        method: n," +
            "        arguments: tc.inputParameters || {}," +
            "        headers: mcpCfg[n].headers || {}};" +
            "    } else if (agentToolCfg[n]) {" +
            "      t.type = 'SUB_WORKFLOW';" +
            "      t.name = agentToolCfg[n].workflowName;" +
            "      t.subWorkflowParam = {name: agentToolCfg[n].workflowName, version: 1};" +
            "      t.inputParameters = {" +
            "        prompt: (tc.inputParameters && tc.inputParameters.request)" +
            "                || JSON.stringify(tc.inputParameters)," +
            "        session_id: $.session_id || ''};" +
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
            "    }" +
            "    if (t.type === 'SIMPLE') { t.inputParameters._agent_state = agentState; }" +
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
            "  if (!raw) return {needs_normalize: true, raw_text: ''};" +
            "  var raw_text;" +
            "  if (typeof raw === 'string') { raw_text = raw; }" +
            "  else if (typeof raw.result === 'string') { raw_text = raw.result; }" +
            "  else { var p = []; for (var k in raw) { p.push(k + ': ' + raw[k]); }" +
            "         raw_text = p.join(', '); }" +
            "  if (typeof raw === 'object' && typeof raw.approved === 'boolean') {" +
            "    return {needs_normalize: false, approved: raw.approved," +
            "            reason: raw.reason || null, raw_text: raw_text};" +
            "  }" +
            "  if (typeof raw === 'object' && typeof raw.approved === 'string') {" +
            "    var a = raw.approved.toLowerCase().trim();" +
            "    if (a === 'true' || a === 'yes' || a === 'y') {" +
            "      return {needs_normalize: false, approved: true, reason: raw.reason || null," +
            "              raw_text: raw_text};" +
            "    }" +
            "    if (a === 'false' || a === 'no' || a === 'n') {" +
            "      return {needs_normalize: false, approved: false, reason: raw.reason || null," +
            "              raw_text: raw_text};" +
            "    }" +
            "  }" +
            "  return {needs_normalize: true, raw_text: raw_text};"
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
                                                     String agentToolConfigJson, String ragConfigJson) {
        return iife(
            "  var httpCfg = " + httpConfigJson + ";" +
            "  var mcpCfg = $.mcpConfig || {};" +
            "  var mediaCfg = " + mediaConfigJson + ";" +
            "  var agentToolCfg = " + agentToolConfigJson + ";" +
            "  var ragCfg = " + ragConfigJson + ";" +
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
            "    } else if (mcpCfg[n]) {" +
            "      t.type = 'CALL_MCP_TOOL';" +
            "      t.name = 'call_mcp_tool';" +
            "      t.inputParameters = {" +
            "        mcpServer: mcpCfg[n].mcpServer || ''," +
            "        method: n," +
            "        arguments: tc.inputParameters || {}," +
            "        headers: mcpCfg[n].headers || {}};" +
            "    } else if (agentToolCfg[n]) {" +
            "      t.type = 'SUB_WORKFLOW';" +
            "      t.name = agentToolCfg[n].workflowName;" +
            "      t.subWorkflowParam = {name: agentToolCfg[n].workflowName, version: 1};" +
            "      t.inputParameters = {" +
            "        prompt: (tc.inputParameters && tc.inputParameters.request)" +
            "                || JSON.stringify(tc.inputParameters)," +
            "        session_id: $.session_id || ''};" +
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
            "    }" +
            "    if (t.type === 'SIMPLE') { t.inputParameters._agent_state = agentState; }" +
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
     * Build approval check script for tool approval flow.
     */
    public static String approvalCheckScript() {
        return iife(
            "  var validated = $.validated;" +
            "  var normalized = $.normalized;" +
            "  var data = (validated && !validated.needs_normalize) ? validated : (normalized || {});" +
            "  return {approved: data.approved === true, reason: data.reason || ''};"
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
}
