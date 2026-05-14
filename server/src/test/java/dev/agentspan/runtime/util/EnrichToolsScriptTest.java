/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Validates the dynamic-fork enrichment script that turns LLM-emitted
 * {@code toolCalls} into Conductor task definitions. The critical
 * contract: a tool name the LLM hallucinated (i.e. not in the configured
 * tool list) must NOT become a SCHEDULED-with-no-poller task. It should
 * become an INLINE error task that returns a model-visible error result.
 */
class EnrichToolsScriptTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private Context graalCtx;

    @BeforeEach
    void setUp() {
        graalCtx = Context.newBuilder("js").allowAllAccess(true).build();
    }

    @AfterEach
    void tearDown() {
        graalCtx.close();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> enrich(String knownNamesJson, String toolCallsJson) throws Exception {
        // All optional config maps are empty so every name falls through to the
        // generic SIMPLE-or-unknown branch. That's the path the harness uses.
        String script =
                JavaScriptBuilder.enrichToolsScript("{}", "{}", "{}", "{}", "{}", "{}", "{}", "{}", knownNamesJson);
        // Wrap so the script's IIFE return is captured AND we get a JSON string
        // back — Graal's Value.toString() is JS source, not JSON.
        String wrapped = "var $ = {"
                + "toolCalls: " + toolCallsJson + ","
                + "agentState: {},"
                + "userPrompt: 'test'"
                + "}; JSON.stringify(" + script + ");";
        Value v = graalCtx.eval("js", wrapped);
        String json = v.asString();
        Map<String, Object> outer = MAPPER.readValue(json, Map.class);
        Object tasks = outer.containsKey("dynamicTasks") ? outer.get("dynamicTasks") : outer.get("tasks");
        return (List<Map<String, Object>>) tasks;
    }

    @Test
    void unknownToolBecomesInlineErrorTask() throws Exception {
        // Configure two known tools; have the LLM call a third name.
        String known = "{\"shell\": true, \"read_file\": true}";
        String toolCalls = "[{\"name\": \"find\", \"taskReferenceName\": \"call_1\","
                + " \"inputParameters\": {\"path\": \"/tmp\"}}]";

        List<Map<String, Object>> tasks = enrich(known, toolCalls);
        assertThat(tasks).hasSize(1);
        Map<String, Object> t = tasks.get(0);
        assertThat(t.get("type")).isEqualTo("INLINE");
        Map<String, Object> ip = (Map<String, Object>) t.get("inputParameters");
        assertThat(ip.get("evaluatorType")).isEqualTo("graaljs");
        String errMsg = (String) ip.get("errorMessage");
        assertThat(errMsg).contains("Unknown tool 'find'");
        assertThat(errMsg).contains("shell");
        assertThat(errMsg).contains("read_file");
    }

    @Test
    void knownToolStaysAsSimpleTask() throws Exception {
        String known = "{\"shell\": true}";
        String toolCalls = "[{\"name\": \"shell\", \"taskReferenceName\": \"call_1\","
                + " \"inputParameters\": {\"command\": \"echo hi\"}}]";

        List<Map<String, Object>> tasks = enrich(known, toolCalls);
        assertThat(tasks).hasSize(1);
        Map<String, Object> t = tasks.get(0);
        assertThat(t.get("type")).isEqualTo("SIMPLE");
        assertThat(t.get("name")).isEqualTo("shell");
    }

    @Test
    void emptyKnownNamesRejectsAllToolCalls() throws Exception {
        // An agent with ``tools=[]`` exposes NO callable tools to the LLM.
        // Any hallucinated tool_call must be rejected as unknown. The
        // previous behavior (passthrough as SIMPLE) was the prefill-only
        // leak: tools registered for prefill execution would dispatch
        // hallucinated calls because the unknown-name check was bypassed
        // whenever knownNames was empty. New contract: empty knownNames
        // means EVERY name is unknown.
        String known = "{}";
        String toolCalls = "[{\"name\": \"anything\", \"taskReferenceName\": \"c1\"," + " \"inputParameters\": {}}]";

        List<Map<String, Object>> tasks = enrich(known, toolCalls);
        assertThat(tasks).hasSize(1);
        Map<String, Object> t = tasks.get(0);
        assertThat(t.get("type"))
                .as("empty knownNames must produce an INLINE error task, not SIMPLE")
                .isEqualTo("INLINE");
        @SuppressWarnings("unchecked")
        Map<String, Object> ip = (Map<String, Object>) t.get("inputParameters");
        assertThat((String) ip.get("errorMessage")).contains("Unknown tool 'anything'");
    }

    @Test
    void prefillOnlyToolHallucinationRejected() throws Exception {
        // Deterministic e2e for the prefill-only leak. Agent declares ONE
        // LLM-callable tool (``write_task_brief``). The model hallucinates
        // a call to ``contextbook_read`` — a tool that's only in
        // ``prefill_tools`` (so a worker IS registered for it, but the LLM
        // was never told about it). The dispatch must NOT route the
        // hallucinated call to the registered prefill worker; it must
        // produce an unknown-tool error visible to the model.
        String known = "{\"write_task_brief\": true}";
        String toolCalls = "[{\"name\": \"contextbook_read\", \"taskReferenceName\": \"call_halluc\","
                + " \"inputParameters\": {\"section\": \"issue_pr\"}}]";

        List<Map<String, Object>> tasks = enrich(known, toolCalls);
        assertThat(tasks).hasSize(1);
        Map<String, Object> t = tasks.get(0);
        assertThat(t.get("type"))
                .as("prefill-only tool hallucinated by LLM must NOT dispatch as SIMPLE — "
                        + "if it did, the prefill worker registration would execute the call")
                .isEqualTo("INLINE");
        @SuppressWarnings("unchecked")
        Map<String, Object> ip = (Map<String, Object>) t.get("inputParameters");
        String err = (String) ip.get("errorMessage");
        assertThat(err).contains("Unknown tool 'contextbook_read'");
        assertThat(err)
                .as("error message lists the agent's actual callable tools, so the model "
                        + "knows what it CAN call going forward")
                .contains("write_task_brief")
                .doesNotContain("contextbook_read'. Available tools: contextbook_read");
    }

    @Test
    void prefillToolAlsoInDeclaredToolsIsCallable() throws Exception {
        // Some agents legitimately list a tool in BOTH prefill_tools AND
        // tools=[..] (the prefill is for first-turn priming; subsequent
        // turns let the LLM call it on demand). Such tools must remain
        // callable — only prefill-ONLY names are blocked.
        String known = "{\"contextbook_read\": true, \"write_task_brief\": true}";
        String toolCalls = "[{\"name\": \"contextbook_read\", \"taskReferenceName\": \"call_1\","
                + " \"inputParameters\": {\"section\": \"issue_pr\"}}]";

        List<Map<String, Object>> tasks = enrich(known, toolCalls);
        assertThat(tasks).hasSize(1);
        assertThat(tasks.get(0).get("type")).isEqualTo("SIMPLE");
        assertThat(tasks.get(0).get("name")).isEqualTo("contextbook_read");
    }

    @Test
    void mixedKnownAndUnknownInOneTurn() throws Exception {
        String known = "{\"shell\": true}";
        String toolCalls = "["
                + "{\"name\": \"shell\", \"taskReferenceName\": \"c1\", \"inputParameters\": {}},"
                + "{\"name\": \"find\",  \"taskReferenceName\": \"c2\", \"inputParameters\": {}}"
                + "]";
        List<Map<String, Object>> tasks = enrich(known, toolCalls);
        assertThat(tasks).hasSize(2);
        assertThat(tasks.get(0).get("type")).isEqualTo("SIMPLE");
        assertThat(tasks.get(1).get("type")).isEqualTo("INLINE");
    }
}
