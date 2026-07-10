// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.conductoross.conductor.ai.enums.OnFail;
import org.conductoross.conductor.ai.enums.Position;
import org.conductoross.conductor.ai.enums.Strategy;
import org.conductoross.conductor.ai.execution.CliConfig;
import org.conductoross.conductor.ai.gate.TextGate;
import org.conductoross.conductor.ai.guardrail.Guardrail;
import org.conductoross.conductor.ai.guardrail.LLMGuardrail;
import org.conductoross.conductor.ai.guardrail.RegexGuardrail;
import org.conductoross.conductor.ai.handoff.OnCondition;
import org.conductoross.conductor.ai.internal.AgentConfigSerializer;
import org.conductoross.conductor.ai.model.CredentialFile;
import org.conductoross.conductor.ai.model.GuardrailDef;
import org.conductoross.conductor.ai.model.GuardrailResult;
import org.conductoross.conductor.ai.model.ToolDef;
import org.conductoross.conductor.ai.openai.GPTAssistantAgent;
import org.conductoross.conductor.ai.plans.Context;
import org.conductoross.conductor.ai.termination.StopMessageTermination;
import org.conductoross.conductor.ai.termination.TerminationResult;
import org.conductoross.conductor.ai.tools.HumanTool;
import org.conductoross.conductor.ai.tools.MediaTools;
import org.conductoross.conductor.ai.tools.WaitForMessageTool;
import org.junit.jupiter.api.Test;

/**
 * Unit tests for AgentConfigSerializer — new parity features.
 *
 * Pure in-process: calls serialize() and asserts on the output map.
 * No server, no LLM, runs in milliseconds.
 *
 * Each test is COUNTERFACTUAL — it must fail if the feature serializes wrong.
 */
class SerializerTest {

    private final AgentConfigSerializer ser = new AgentConfigSerializer();

    // ── Helpers ───────────────────────────────────────────────────────────

    private ToolDef workerTool(String name) {
        return ToolDef.builder()
                .name(name)
                .description("A worker tool.")
                .inputSchema(Map.of("type", "object", "properties", Map.of()))
                .toolType("worker")
                .func(input -> input)
                .build();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> tool(Map<String, Object> out, String name) {
        List<Map<String, Object>> tools = (List<Map<String, Object>>) out.get("tools");
        assertNotNull(tools, "serialized output has no 'tools' key");
        return tools.stream()
                .filter(t -> name.equals(t.get("name")))
                .findFirst()
                .orElseGet(() -> {
                    fail("Tool '" + name + "' not found. Available: "
                            + tools.stream().map(t -> (String) t.get("name")).collect(Collectors.toList()));
                    return null;
                });
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> guardrail(Map<String, Object> out, String name) {
        List<Map<String, Object>> guards = (List<Map<String, Object>>) out.get("guardrails");
        assertNotNull(guards, "serialized output has no 'guardrails' key");
        return guards.stream()
                .filter(g -> name.equals(g.get("name")))
                .findFirst()
                .orElseGet(() -> {
                    fail("Guardrail '" + name + "' not found. Available: "
                            + guards.stream().map(g -> (String) g.get("name")).collect(Collectors.toList()));
                    return null;
                });
    }

    // ── Stateful ─────────────────────────────────────────────────────────

    @Test
    void stateful_propagates_true_to_each_tool() {
        Agent agent = Agent.builder()
                .name("stateful_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .stateful(true)
                .tools(List.of(workerTool("tool_a"), workerTool("tool_b")))
                .build();

        Map<String, Object> out = ser.serialize(agent);

        assertEquals(
                true, tool(out, "tool_a").get("stateful"), "tool_a.stateful should be true when agent.stateful=true");
        assertEquals(
                true, tool(out, "tool_b").get("stateful"), "tool_b.stateful should be true when agent.stateful=true");
    }

    @Test
    void non_stateful_agent_does_not_set_tool_stateful() {
        Agent agent = Agent.builder()
                .name("normal_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .tools(List.of(workerTool("tool_c")))
                .build();

        Map<String, Object> out = ser.serialize(agent);

        assertNull(tool(out, "tool_c").get("stateful"), "tool.stateful should be null/absent for a non-stateful agent");
    }

    // ── CLI config ──────────────────────────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void cli_config_injects_run_command_worker_tool() {
        Agent agent = Agent.builder()
                .name("ops")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .cliConfig(CliConfig.builder()
                        .allowedCommands(List.of("git", "gh"))
                        .timeout(60)
                        .build())
                .build();

        Map<String, Object> out = ser.serialize(agent);

        // Agent-level cliConfig block still serialized.
        Map<String, Object> cliMap = (Map<String, Object>) out.get("cliConfig");
        assertNotNull(cliMap, "cliConfig block must be serialized");
        assertEquals(List.of("git", "gh"), cliMap.get("allowedCommands"));

        // The {name}_run_command worker tool must be injected so the LLM can call it.
        Map<String, Object> rc = tool(out, "ops_run_command");
        assertEquals("worker", rc.get("toolType"));
        // Allowed commands are advertised sorted (parity with Python/TS/C#).
        assertTrue(
                ((String) rc.get("description")).contains("gh, git"),
                "description should advertise the allowed commands: " + rc.get("description"));
        Map<String, Object> schema = (Map<String, Object>) rc.get("inputSchema");
        Map<String, Object> props = (Map<String, Object>) schema.get("properties");
        assertTrue(
                props.containsKey("command")
                        && props.containsKey("args")
                        && props.containsKey("cwd")
                        && props.containsKey("shell"),
                "input schema must expose command/args/cwd/shell");
        assertEquals(List.of("command"), schema.get("required"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void disabled_cli_config_does_not_inject_run_command_tool() {
        Agent agent = Agent.builder()
                .name("ops2")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .cliConfig(CliConfig.builder()
                        .enabled(false)
                        .allowedCommands(List.of("git"))
                        .build())
                .build();

        Map<String, Object> out = ser.serialize(agent);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) out.get("tools");
        boolean hasRunCommand = tools != null && tools.stream().anyMatch(t -> "ops2_run_command".equals(t.get("name")));
        assertFalse(hasRunCommand, "disabled cliConfig must not inject a run_command tool");
    }

    // ── baseUrl ───────────────────────────────────────────────────────────

    @Test
    void base_url_serialized() {
        Agent agent = Agent.builder()
                .name("baseurl_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .baseUrl("http://proxy.internal/v1")
                .build();

        Map<String, Object> out = ser.serialize(agent);

        assertEquals("http://proxy.internal/v1", out.get("baseUrl"), "baseUrl should appear in serialized output");
    }

    @Test
    void missing_base_url_not_serialized() {
        Agent agent = Agent.builder()
                .name("no_baseurl_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .build();

        Map<String, Object> out = ser.serialize(agent);

        assertNull(out.get("baseUrl"), "baseUrl should be absent when not set");
    }

    // ── TextGate ──────────────────────────────────────────────────────────

    @Test
    void text_gate_serialized_with_all_fields() {
        Agent agent = Agent.builder()
                .name("gate_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .gate(new TextGate("STOP", false))
                .build();

        Map<String, Object> out = ser.serialize(agent);

        @SuppressWarnings("unchecked")
        Map<String, Object> gate = (Map<String, Object>) out.get("gate");
        assertNotNull(gate, "gate should be serialized");
        assertEquals("text_contains", gate.get("type"));
        assertEquals("STOP", gate.get("text"));
        assertEquals(false, gate.get("caseSensitive"));
    }

    @Test
    void text_gate_case_sensitive_default() {
        Agent agent = Agent.builder()
                .name("gate_cs_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .gate(new TextGate("DONE"))
                .build();

        Map<String, Object> out = ser.serialize(agent);

        @SuppressWarnings("unchecked")
        Map<String, Object> gate = (Map<String, Object>) out.get("gate");
        assertEquals(true, gate.get("caseSensitive"), "Default TextGate should be case-sensitive");
    }

    // ── before/after agent callbacks ──────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void before_agent_callback_serialized() {
        Agent agent = Agent.builder()
                .name("before_cb_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .beforeAgentCallback(ctx -> ctx)
                .build();

        Map<String, Object> out = ser.serialize(agent);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) out.get("callbacks");
        assertNotNull(callbacks, "callbacks should be present");
        assertEquals(1, callbacks.size());
        assertEquals("before_agent", callbacks.get(0).get("position"));
        assertEquals("before_cb_agent_before_agent", callbacks.get(0).get("taskName"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void after_agent_callback_serialized() {
        Agent agent = Agent.builder()
                .name("after_cb_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .afterAgentCallback(ctx -> ctx)
                .build();

        Map<String, Object> out = ser.serialize(agent);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) out.get("callbacks");
        assertNotNull(callbacks, "callbacks should be present");
        assertEquals(1, callbacks.size());
        assertEquals("after_agent", callbacks.get(0).get("position"));
        assertEquals("after_cb_agent_after_agent", callbacks.get(0).get("taskName"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void both_callbacks_produce_two_entries() {
        Agent agent = Agent.builder()
                .name("both_cb_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .beforeAgentCallback(ctx -> ctx)
                .afterAgentCallback(ctx -> ctx)
                .build();

        Map<String, Object> out = ser.serialize(agent);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) out.get("callbacks");
        assertNotNull(callbacks);
        assertEquals(2, callbacks.size(), "Both before and after agent callbacks must produce 2 entries");

        List<String> positions =
                callbacks.stream().map(cb -> (String) cb.get("position")).collect(Collectors.toList());
        assertTrue(positions.contains("before_agent"));
        assertTrue(positions.contains("after_agent"));
    }

    @Test
    void no_callbacks_absent_from_output() {
        Agent agent = Agent.builder()
                .name("no_cb_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .build();

        Map<String, Object> out = ser.serialize(agent);

        assertNull(out.get("callbacks"), "callbacks key should be absent when none are set");
    }

    // ── StopMessageTermination ────────────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void stop_message_termination_serialized() {
        Agent agent = Agent.builder()
                .name("stop_msg_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .termination(StopMessageTermination.of("DONE"))
                .build();

        Map<String, Object> out = ser.serialize(agent);

        Map<String, Object> term = (Map<String, Object>) out.get("termination");
        assertNotNull(term, "termination should be present");
        assertEquals("stop_message", term.get("type"));
        assertEquals("DONE", term.get("stopMessage"));
    }

    @Test
    void stop_message_termination_to_map() {
        StopMessageTermination t = StopMessageTermination.of("EXIT");
        Map<String, Object> map = t.toMap();
        assertEquals("stop_message", map.get("type"));
        assertEquals("EXIT", map.get("stopMessage"));
    }

    // ── TerminationResult ─────────────────────────────────────────────────

    @Test
    void termination_result_stop() {
        TerminationResult r = TerminationResult.stop("iteration limit");
        assertTrue(r.isShouldTerminate());
        assertEquals("iteration limit", r.getReason());
    }

    @Test
    void termination_result_continue() {
        TerminationResult r = TerminationResult.continueRunning();
        assertFalse(r.isShouldTerminate());
        assertNull(r.getReason());
    }

    // ── RegexGuardrail ────────────────────────────────────────────────────

    @Test
    void regex_guardrail_type_and_patterns_at_top_level() {
        GuardrailDef guard = RegexGuardrail.builder()
                .name("pii_guard")
                .patterns("[\\w.+-]+@[\\w-]+\\.[\\w.-]+")
                .position(Position.OUTPUT)
                .onFail(OnFail.RETRY)
                .build();

        Agent agent = Agent.builder()
                .name("regex_guard_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .guardrails(List.of(guard))
                .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> g = guardrail(out, "pii_guard");

        assertEquals("regex", g.get("guardrailType"));
        assertEquals("output", g.get("position"));
        // patterns is inlined at top level, NOT nested under config
        assertNotNull(g.get("patterns"), "patterns should be at top level of guardrail map");
        assertNull(g.get("config"), "there should be no nested 'config' key — patterns are inlined");
    }

    @Test
    void regex_guardrail_block_mode_default() {
        GuardrailDef guard = RegexGuardrail.builder()
                .name("block_guard")
                .patterns("bad_word")
                .build();

        Agent agent = Agent.builder()
                .name("block_guard_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .guardrails(List.of(guard))
                .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> g = guardrail(out, "block_guard");
        assertEquals("block", g.get("mode"), "Default mode should be 'block'");
    }

    @Test
    void regex_guardrail_allow_mode() {
        GuardrailDef guard = RegexGuardrail.builder()
                .name("allow_guard")
                .patterns("^\\s*[\\{\\[]")
                .mode("allow")
                .build();

        Agent agent = Agent.builder()
                .name("allow_guard_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .guardrails(List.of(guard))
                .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> g = guardrail(out, "allow_guard");
        assertEquals("allow", g.get("mode"));
    }

    @Test
    void regex_guardrail_requires_patterns() {
        assertThrows(
                IllegalArgumentException.class,
                () -> RegexGuardrail.builder().name("empty").build());
    }

    // ── LLMGuardrail ──────────────────────────────────────────────────────

    @Test
    void llm_guardrail_type_model_policy_at_top_level() {
        GuardrailDef guard = LLMGuardrail.builder()
                .name("safety_guard")
                .model("anthropic/claude-sonnet-4-6")
                .policy("Reject harmful content.")
                .position(Position.OUTPUT)
                .onFail(OnFail.RETRY)
                .build();

        Agent agent = Agent.builder()
                .name("llm_guard_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .guardrails(List.of(guard))
                .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> g = guardrail(out, "safety_guard");

        assertEquals("llm", g.get("guardrailType"));
        // model and policy are inlined at top level, NOT nested under config
        assertEquals("anthropic/claude-sonnet-4-6", g.get("model"), "model should be at top level of guardrail map");
        assertEquals("Reject harmful content.", g.get("policy"), "policy should be at top level of guardrail map");
        assertNull(g.get("config"), "there should be no nested 'config' key");
    }

    @Test
    void llm_guardrail_requires_model_and_policy() {
        assertThrows(
                IllegalArgumentException.class,
                () -> LLMGuardrail.builder().name("no_model").policy("test").build());
        assertThrows(IllegalArgumentException.class, () -> LLMGuardrail.builder()
                .name("no_policy")
                .model("anthropic/claude-sonnet-4-6")
                .build());
    }

    // ── OnCondition handoff ───────────────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void on_condition_handoff_serialized_with_target() {
        Agent supervisor = Agent.builder()
                .name("supervisor")
                .model("anthropic/claude-sonnet-4-6")
                .build();
        Agent worker = Agent.builder()
                .name("worker")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .handoffs(List.of(new OnCondition("supervisor", ctx -> Boolean.TRUE.equals(ctx.get("escalate")))))
                .build();

        Agent team = Agent.builder()
                .name("team")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .agents(supervisor, worker)
                .strategy(Strategy.HANDOFF)
                .build();

        Map<String, Object> out = ser.serialize(team);
        List<Map<String, Object>> agents = (List<Map<String, Object>>) out.get("agents");
        assertNotNull(agents);

        Map<String, Object> workerOut = agents.stream()
                .filter(a -> "worker".equals(a.get("name")))
                .findFirst()
                .orElseGet(() -> {
                    fail("worker not found");
                    return null;
                });

        List<Map<String, Object>> handoffs = (List<Map<String, Object>>) workerOut.get("handoffs");
        assertNotNull(handoffs, "handoffs should be serialized");
        assertFalse(handoffs.isEmpty());
        assertEquals("supervisor", handoffs.get(0).get("target"));
    }

    // ── MediaTools ────────────────────────────────────────────────────────

    @Test
    void image_tool_has_generate_image_type() {
        ToolDef img = MediaTools.imageTool("my_img", "Generate image", "openai", "dall-e-3");
        assertEquals("generate_image", img.getToolType(), "imageTool must have toolType='generate_image'");
    }

    @Test
    void audio_tool_has_generate_audio_type() {
        ToolDef aud = MediaTools.audioTool("my_audio", "Speak text", "openai", "tts-1");
        assertEquals("generate_audio", aud.getToolType(), "audioTool must have toolType='generate_audio'");
    }

    @Test
    void video_tool_has_generate_video_type() {
        ToolDef vid = MediaTools.videoTool("my_video", "Make video", "openai", "sora-2");
        assertEquals("generate_video", vid.getToolType(), "videoTool must have toolType='generate_video'");
    }

    @Test
    void pdf_tool_has_generate_pdf_type() {
        ToolDef pdf = MediaTools.pdfTool();
        assertEquals("generate_pdf", pdf.getToolType(), "pdfTool must have toolType='generate_pdf'");
    }

    @Test
    void media_tools_serialized_in_agent() {
        ToolDef img = MediaTools.imageTool("img_tool", "image", "openai", "dall-e-3");
        Agent agent = Agent.builder()
                .name("media_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .tools(List.of(img))
                .build();

        Map<String, Object> out = ser.serialize(agent);
        assertEquals("generate_image", tool(out, "img_tool").get("toolType"));
    }

    // ── WaitForMessageTool ────────────────────────────────────────────────

    @Test
    void wait_for_message_tool_type() {
        ToolDef wait = WaitForMessageTool.create("wait_msgs", "Wait", 5, true);
        assertEquals("pull_workflow_messages", wait.getToolType());
    }

    @Test
    void wait_for_message_tool_serialized_in_agent() {
        ToolDef wait = WaitForMessageTool.create("wait_tool", "Wait for messages");
        Agent agent = Agent.builder()
                .name("wait_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .tools(List.of(wait))
                .build();

        Map<String, Object> out = ser.serialize(agent);
        assertEquals("pull_workflow_messages", tool(out, "wait_tool").get("toolType"));
    }

    // ── HumanTool ─────────────────────────────────────────────────────────

    @Test
    void human_tool_type() {
        ToolDef human = HumanTool.create("ask_human", "Ask a human.");
        assertEquals("human", human.getToolType());
    }

    @Test
    void human_tool_serialized_in_agent() {
        ToolDef human = HumanTool.create("human_tool", "Ask human");
        Agent agent = Agent.builder()
                .name("human_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("test")
                .tools(List.of(human))
                .build();

        Map<String, Object> out = ser.serialize(agent);
        assertEquals("human", tool(out, "human_tool").get("toolType"));
    }

    // ── GPTAssistantAgent ─────────────────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void gpt_assistant_sets_agent_type_metadata() {
        Agent agent = GPTAssistantAgent.create("my_assistant")
                .model("gpt-4o")
                .instructions("You are helpful.")
                .build();

        Map<String, Object> out = ser.serialize(agent);

        Map<String, Object> metadata = (Map<String, Object>) out.get("metadata");
        assertNotNull(metadata, "GPTAssistantAgent must set metadata");
        assertEquals("gpt_assistant", metadata.get("_agent_type"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void gpt_assistant_with_existing_id_sets_assistant_id_in_metadata() {
        Agent agent = GPTAssistantAgent.create("existing_assistant")
                .assistantId("asst_abc123")
                .build();

        Map<String, Object> out = ser.serialize(agent);

        Map<String, Object> metadata = (Map<String, Object>) out.get("metadata");
        assertNotNull(metadata);
        assertEquals("asst_abc123", metadata.get("_assistant_id"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void gpt_assistant_has_call_tool() {
        Agent agent = GPTAssistantAgent.create("tool_assistant").model("gpt-4o").build();

        Map<String, Object> out = ser.serialize(agent);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) out.get("tools");
        assertNotNull(tools);
        boolean hasCallTool = tools.stream().anyMatch(t -> ((String) t.get("name")).endsWith("_assistant_call"));
        assertTrue(hasCallTool, "GPTAssistantAgent must have a '{name}_assistant_call' tool");
    }

    @Test
    void gpt_assistant_normalizes_model_prefix() {
        Agent withPrefix = GPTAssistantAgent.create("a1").model("openai/gpt-4o").build();
        Agent withoutPrefix = GPTAssistantAgent.create("a2").model("gpt-4o").build();

        Map<String, Object> out1 = ser.serialize(withPrefix);
        Map<String, Object> out2 = ser.serialize(withoutPrefix);

        assertEquals("openai/gpt-4o", out1.get("model"));
        assertEquals(
                "openai/gpt-4o",
                out2.get("model"),
                "model without 'openai/' prefix should be normalized to 'openai/gpt-4o'");
    }

    // ── Skill agent ───────────────────────────────────────────────────────

    @Test
    void skill_agent_uses_framework_fast_path() {
        Agent skillAgent = Agent.builder()
                .name("my_skill")
                .model("anthropic/claude-sonnet-4-6")
                .framework("skill")
                .frameworkConfig(Map.of("skillMd", "# My Skill\nDo things."))
                .build();

        Map<String, Object> out = ser.serialize(skillAgent);

        assertEquals("skill", out.get("_framework"), "Skill agent must serialize _framework='skill'");
        assertEquals("my_skill", out.get("name"));
        assertNotNull(out.get("skillMd"), "frameworkConfig contents should be inlined into the output");
    }

    // ── CredentialFile ────────────────────────────────────────────────────

    @Test
    void credential_file_fields_preserved() {
        CredentialFile cf = new CredentialFile("MY_API_KEY", "secrets/key.txt", null);
        assertEquals("MY_API_KEY", cf.getEnvVar());
        assertEquals("secrets/key.txt", cf.getRelativePath());
        assertNull(cf.getContent());
    }

    @Test
    void credential_file_with_content() {
        CredentialFile cf = new CredentialFile("MY_KEY", null, "secret-value");
        CredentialFile filled = cf.withContent("new-secret");
        assertEquals("new-secret", filled.getContent());
        assertEquals("MY_KEY", filled.getEnvVar());
    }

    // --- Conductor client base-path normalization (server URL now lives on the client) ---

    @Test
    void client_default_base_path_ends_with_api() {
        assertEquals(
                "http://localhost:6767/api",
                AgentRuntime.client("http://localhost:6767").getBasePath());
    }

    @Test
    void client_strips_trailing_api_then_re_appends() {
        assertEquals(
                "http://localhost:6767/api",
                AgentRuntime.client("http://localhost:6767/api").getBasePath());
    }

    @Test
    void client_strips_trailing_slash_and_api() {
        assertEquals(
                "http://localhost:6767/api",
                AgentRuntime.client("http://localhost:6767/api/").getBasePath());
    }

    @Test
    void client_plain_url_gets_api_suffix() {
        assertEquals(
                "http://localhost:6767/api",
                AgentRuntime.client("http://localhost:6767").getBasePath());
    }

    // --- CliConfig serialization ---

    @Test
    @SuppressWarnings("unchecked")
    void cliConfig_serialized_as_cliConfig_block() {
        Agent agent = Agent.builder()
                .name("ops")
                .model("openai/gpt-4o")
                .cliConfig(CliConfig.builder()
                        .allowedCommands(List.of("git", "gh"))
                        .timeout(60)
                        .allowShell(false)
                        .build())
                .build();
        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> cli = (Map<String, Object>) out.get("cliConfig");
        assertNotNull(cli, "cliConfig block must be present");
        assertEquals(true, cli.get("enabled"));
        assertEquals(List.of("git", "gh"), cli.get("allowedCommands"));
        assertEquals(60, cli.get("timeout"));
        assertEquals(false, cli.get("allowShell"));
        assertNull(out.get("codeExecution"), "cliConfig must not bleed into codeExecution");
    }

    @Test
    void cliConfig_absent_when_not_set() {
        Agent agent = Agent.builder().name("a").model("openai/gpt-4o").build();
        Map<String, Object> out = ser.serialize(agent);
        assertNull(out.get("cliConfig"));
    }

    // --- Guardrail (custom / external) ---

    @Test
    @SuppressWarnings("unchecked")
    void guardrail_custom_serialized_as_custom_type() {
        GuardrailDef g =
                Guardrail.of("no_bad_words", content -> GuardrailResult.pass()).build();
        Agent agent = Agent.builder()
                .name("a")
                .model("openai/gpt-4o")
                .guardrails(List.of(g))
                .build();
        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> gMap = guardrail(out, "no_bad_words");
        assertEquals("custom", gMap.get("guardrailType"));
        assertEquals("output", gMap.get("position"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void guardrail_external_serialized_as_external_type() {
        GuardrailDef g =
                Guardrail.external("corporate_safety").position(Position.INPUT).build();
        Agent agent = Agent.builder()
                .name("a")
                .model("openai/gpt-4o")
                .guardrails(List.of(g))
                .build();
        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> gMap = guardrail(out, "corporate_safety");
        assertEquals("external", gMap.get("guardrailType"));
        assertEquals("input", gMap.get("position"));
    }

    // ── retry policy serialization ────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void tool_retry_policy_serialized_when_non_default() {
        ToolDef t = ToolDef.builder()
                .name("fetch_data")
                .description("Fetch data")
                .inputSchema(Map.of("type", "object", "properties", Map.of()))
                .retryCount(5)
                .retryDelaySeconds(10)
                .retryPolicy("exponential_backoff")
                .build();
        Agent agent = Agent.builder()
                .name("a")
                .model("openai/gpt-4o")
                .tools(List.of(t))
                .build();
        Map<String, Object> out = ser.serialize(agent);
        List<Map<String, Object>> tools = (List<Map<String, Object>>) out.get("tools");
        Map<String, Object> toolMap = tools.get(0);
        assertEquals(5, toolMap.get("retryCount"));
        assertEquals(10, toolMap.get("retryDelaySeconds"));
        assertEquals("exponential_backoff", toolMap.get("retryPolicy"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void tool_retry_policy_omitted_when_default() {
        ToolDef t = ToolDef.builder()
                .name("fetch_data")
                .description("Fetch data")
                .inputSchema(Map.of("type", "object", "properties", Map.of()))
                .build();
        Agent agent = Agent.builder()
                .name("a")
                .model("openai/gpt-4o")
                .tools(List.of(t))
                .build();
        Map<String, Object> out = ser.serialize(agent);
        List<Map<String, Object>> tools = (List<Map<String, Object>>) out.get("tools");
        Map<String, Object> toolMap = tools.get(0);
        assertFalse(toolMap.containsKey("retryCount"));
        assertFalse(toolMap.containsKey("retryDelaySeconds"));
        assertFalse(toolMap.containsKey("retryPolicy"));
    }

    // ── plannerContext (PLAN_EXECUTE) ─────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void planner_context_emitted_with_text_and_url_entries() {
        // Mirrors the Python + TS serializer tests. The wire shape MUST be
        // byte-equal across SDKs so the server compiler sees the same
        // payload regardless of language.
        Agent planner = Agent.builder()
                .name("planner_sub")
                .model("anthropic/claude-sonnet-4-6")
                .build();
        ToolDef stub = ToolDef.builder()
                .name("stub")
                .description("stub")
                .inputSchema(Map.of("type", "object", "properties", Map.of()))
                .build();
        Agent harness = Agent.builder()
                .name("h")
                .model("anthropic/claude-sonnet-4-6")
                .strategy(Strategy.PLAN_EXECUTE)
                .planner(planner)
                .tools(List.of(stub))
                .plannerContext(List.of(
                        Context.text("inline rule"),
                        Context.builder()
                                .url("https://confluence.example.com/onboarding")
                                .header("Authorization", "Bearer ${CONFLUENCE_TOKEN}")
                                .required(false)
                                .maxBytes(8192)
                                .build()))
                .build();
        Map<String, Object> out = ser.serialize(harness);
        List<Map<String, Object>> ctx = (List<Map<String, Object>>) out.get("plannerContext");
        assertEquals(2, ctx.size());
        assertEquals(Map.of("text", "inline rule"), ctx.get(0));
        Map<String, Object> urlEntry = ctx.get(1);
        assertEquals("https://confluence.example.com/onboarding", urlEntry.get("url"));
        // Credential placeholder MUST pass through verbatim — server escapes.
        assertEquals(Map.of("Authorization", "Bearer ${CONFLUENCE_TOKEN}"), urlEntry.get("headers"));
        assertEquals(false, urlEntry.get("required"));
        assertEquals(8192, urlEntry.get("maxBytes"));
    }

    @Test
    void planner_context_omitted_when_unset() {
        // Counterfactual: without plannerContext the field MUST NOT appear
        // on the wire. Pairs with the positive test — pins the gating.
        Agent planner = Agent.builder()
                .name("planner_sub")
                .model("anthropic/claude-sonnet-4-6")
                .build();
        ToolDef stub = ToolDef.builder()
                .name("stub")
                .description("stub")
                .inputSchema(Map.of("type", "object", "properties", Map.of()))
                .build();
        Agent harness = Agent.builder()
                .name("h")
                .model("anthropic/claude-sonnet-4-6")
                .strategy(Strategy.PLAN_EXECUTE)
                .planner(planner)
                .tools(List.of(stub))
                .build();
        Map<String, Object> out = ser.serialize(harness);
        assertFalse(out.containsKey("plannerContext"));
    }

    @Test
    void planner_context_rejected_on_non_plan_execute_strategy() {
        // Same guard shape as planner=/fallback= — setting plannerContext
        // on anything other than PLAN_EXECUTE is a silent bug.
        Agent sub =
                Agent.builder().name("sub").model("anthropic/claude-sonnet-4-6").build();
        IllegalArgumentException e = assertThrows(IllegalArgumentException.class, () -> Agent.builder()
                .name("h")
                .model("anthropic/claude-sonnet-4-6")
                .strategy(Strategy.HANDOFF)
                .agents(List.of(sub))
                .plannerContext("rule")
                .build());
        assertTrue(e.getMessage().contains("PLAN_EXECUTE"));
    }

    // ── Parity fields: reasoningEffort, maskedFields, contextWindowBudget, memory ──

    @Test
    @SuppressWarnings("unchecked")
    void parity_fields_serialized() {
        org.conductoross.conductor.ai.model.ConversationMemory memory =
                new org.conductoross.conductor.ai.model.ConversationMemory(20)
                        .addSystem("You are concise.")
                        .addUser("hi");

        Agent agent = Agent.builder()
                .name("parity_agent")
                .model("openai/o3-mini")
                .instructions("test")
                .reasoningEffort("high")
                .maskedFields("ssn", "card_number")
                .contextWindowBudget(8000)
                .memory(memory)
                .build();

        Map<String, Object> out = ser.serialize(agent);

        assertEquals("high", out.get("reasoningEffort"), "reasoningEffort must serialize");
        assertEquals(List.of("ssn", "card_number"), out.get("maskedFields"), "maskedFields must serialize");
        assertEquals(8000, out.get("contextWindowBudget"), "contextWindowBudget must serialize");

        Map<String, Object> mem = (Map<String, Object>) out.get("memory");
        assertNotNull(mem, "memory must serialize as a map");
        assertEquals(20, mem.get("maxMessages"), "memory.maxMessages must serialize");
        List<Map<String, Object>> msgs = (List<Map<String, Object>>) mem.get("messages");
        assertEquals(2, msgs.size(), "memory.messages must carry both messages");
        assertEquals("system", msgs.get(0).get("role"));
        assertEquals("You are concise.", msgs.get(0).get("message"));
        assertEquals("user", msgs.get(1).get("role"));
    }

    @Test
    void parity_fields_absent_when_unset() {
        Agent agent = Agent.builder()
                .name("plain_agent")
                .model("anthropic/claude-sonnet-4-6")
                .build();
        Map<String, Object> out = ser.serialize(agent);
        assertFalse(out.containsKey("reasoningEffort"), "reasoningEffort omitted when unset");
        assertFalse(out.containsKey("maskedFields"), "maskedFields omitted when unset");
        assertFalse(out.containsKey("contextWindowBudget"), "contextWindowBudget omitted when unset");
        assertFalse(out.containsKey("memory"), "memory omitted when unset");
    }
}
