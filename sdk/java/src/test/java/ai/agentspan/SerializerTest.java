// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan;

import ai.agentspan.enums.OnFail;
import ai.agentspan.enums.Position;
import ai.agentspan.enums.Strategy;
import ai.agentspan.execution.CliConfig;
import ai.agentspan.gate.TextGate;
import ai.agentspan.guardrail.Guardrail;
import ai.agentspan.guardrail.LLMGuardrail;
import ai.agentspan.guardrail.RegexGuardrail;
import ai.agentspan.model.GuardrailResult;
import ai.agentspan.handoff.OnCondition;
import ai.agentspan.internal.AgentConfigSerializer;
import ai.agentspan.model.CredentialFile;
import ai.agentspan.model.GuardrailDef;
import ai.agentspan.model.ToolDef;
import ai.agentspan.openai.GPTAssistantAgent;
import ai.agentspan.skill.Skill;
import ai.agentspan.termination.StopMessageTermination;
import ai.agentspan.termination.TerminationResult;
import ai.agentspan.tools.HumanTool;
import ai.agentspan.tools.MediaTools;
import ai.agentspan.tools.WaitForMessageTool;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

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
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .stateful(true)
            .tools(List.of(workerTool("tool_a"), workerTool("tool_b")))
            .build();

        Map<String, Object> out = ser.serialize(agent);

        assertEquals(true, tool(out, "tool_a").get("stateful"),
            "tool_a.stateful should be true when agent.stateful=true");
        assertEquals(true, tool(out, "tool_b").get("stateful"),
            "tool_b.stateful should be true when agent.stateful=true");
    }

    @Test
    void non_stateful_agent_does_not_set_tool_stateful() {
        Agent agent = Agent.builder()
            .name("normal_agent")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .tools(List.of(workerTool("tool_c")))
            .build();

        Map<String, Object> out = ser.serialize(agent);

        assertNull(tool(out, "tool_c").get("stateful"),
            "tool.stateful should be null/absent for a non-stateful agent");
    }

    // ── baseUrl ───────────────────────────────────────────────────────────

    @Test
    void base_url_serialized() {
        Agent agent = Agent.builder()
            .name("baseurl_agent")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .baseUrl("http://proxy.internal/v1")
            .build();

        Map<String, Object> out = ser.serialize(agent);

        assertEquals("http://proxy.internal/v1", out.get("baseUrl"),
            "baseUrl should appear in serialized output");
    }

    @Test
    void missing_base_url_not_serialized() {
        Agent agent = Agent.builder()
            .name("no_baseurl_agent")
            .model("openai/gpt-4o-mini")
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
            .model("openai/gpt-4o-mini")
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
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .gate(new TextGate("DONE"))
            .build();

        Map<String, Object> out = ser.serialize(agent);

        @SuppressWarnings("unchecked")
        Map<String, Object> gate = (Map<String, Object>) out.get("gate");
        assertEquals(true, gate.get("caseSensitive"),
            "Default TextGate should be case-sensitive");
    }

    // ── before/after agent callbacks ──────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void before_agent_callback_serialized() {
        Agent agent = Agent.builder()
            .name("before_cb_agent")
            .model("openai/gpt-4o-mini")
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
            .model("openai/gpt-4o-mini")
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
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .beforeAgentCallback(ctx -> ctx)
            .afterAgentCallback(ctx -> ctx)
            .build();

        Map<String, Object> out = ser.serialize(agent);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) out.get("callbacks");
        assertNotNull(callbacks);
        assertEquals(2, callbacks.size(), "Both before and after agent callbacks must produce 2 entries");

        List<String> positions = callbacks.stream()
            .map(cb -> (String) cb.get("position"))
            .collect(Collectors.toList());
        assertTrue(positions.contains("before_agent"));
        assertTrue(positions.contains("after_agent"));
    }

    @Test
    void no_callbacks_absent_from_output() {
        Agent agent = Agent.builder()
            .name("no_cb_agent")
            .model("openai/gpt-4o-mini")
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
            .model("openai/gpt-4o-mini")
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
            .model("openai/gpt-4o-mini")
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
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .guardrails(List.of(guard))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> g = guardrail(out, "block_guard");
        assertEquals("block", g.get("mode"),
            "Default mode should be 'block'");
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
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .guardrails(List.of(guard))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> g = guardrail(out, "allow_guard");
        assertEquals("allow", g.get("mode"));
    }

    @Test
    void regex_guardrail_requires_patterns() {
        assertThrows(IllegalArgumentException.class, () ->
            RegexGuardrail.builder().name("empty").build()
        );
    }

    // ── LLMGuardrail ──────────────────────────────────────────────────────

    @Test
    void llm_guardrail_type_model_policy_at_top_level() {
        GuardrailDef guard = LLMGuardrail.builder()
            .name("safety_guard")
            .model("openai/gpt-4o-mini")
            .policy("Reject harmful content.")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .build();

        Agent agent = Agent.builder()
            .name("llm_guard_agent")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .guardrails(List.of(guard))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> g = guardrail(out, "safety_guard");

        assertEquals("llm", g.get("guardrailType"));
        // model and policy are inlined at top level, NOT nested under config
        assertEquals("openai/gpt-4o-mini", g.get("model"),
            "model should be at top level of guardrail map");
        assertEquals("Reject harmful content.", g.get("policy"),
            "policy should be at top level of guardrail map");
        assertNull(g.get("config"), "there should be no nested 'config' key");
    }

    @Test
    void llm_guardrail_requires_model_and_policy() {
        assertThrows(IllegalArgumentException.class, () ->
            LLMGuardrail.builder().name("no_model").policy("test").build()
        );
        assertThrows(IllegalArgumentException.class, () ->
            LLMGuardrail.builder().name("no_policy").model("openai/gpt-4o-mini").build()
        );
    }

    // ── OnCondition handoff ───────────────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void on_condition_handoff_serialized_with_target() {
        Agent supervisor = Agent.builder().name("supervisor").model("openai/gpt-4o-mini").build();
        Agent worker = Agent.builder()
            .name("worker")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .handoffs(List.of(new OnCondition("supervisor",
                ctx -> Boolean.TRUE.equals(ctx.get("escalate")))))
            .build();

        Agent team = Agent.builder()
            .name("team")
            .model("openai/gpt-4o-mini")
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
            .orElseGet(() -> { fail("worker not found"); return null; });

        List<Map<String, Object>> handoffs = (List<Map<String, Object>>) workerOut.get("handoffs");
        assertNotNull(handoffs, "handoffs should be serialized");
        assertFalse(handoffs.isEmpty());
        assertEquals("supervisor", handoffs.get(0).get("target"));
    }

    // ── UserProxyAgent ────────────────────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void user_proxy_agent_sets_metadata() {
        Agent proxy = UserProxyAgent.create("human_user", "ALWAYS", "Continue.", "openai/gpt-4o-mini");
        Map<String, Object> out = ser.serialize(proxy);

        Map<String, Object> metadata = (Map<String, Object>) out.get("metadata");
        assertNotNull(metadata, "UserProxyAgent must set metadata");
        assertEquals("user_proxy", metadata.get("_agent_type"));
        assertEquals("ALWAYS", metadata.get("_human_input_mode"));
    }

    @Test
    void user_proxy_agent_rejects_invalid_mode() {
        assertThrows(IllegalArgumentException.class, () ->
            UserProxyAgent.create("u", "INVALID_MODE", "ok", "openai/gpt-4o-mini")
        );
    }

    // ── MediaTools ────────────────────────────────────────────────────────

    @Test
    void image_tool_has_generate_image_type() {
        ToolDef img = MediaTools.imageTool("my_img", "Generate image", "openai", "dall-e-3");
        assertEquals("generate_image", img.getToolType(),
            "imageTool must have toolType='generate_image'");
    }

    @Test
    void audio_tool_has_generate_audio_type() {
        ToolDef aud = MediaTools.audioTool("my_audio", "Speak text", "openai", "tts-1");
        assertEquals("generate_audio", aud.getToolType(),
            "audioTool must have toolType='generate_audio'");
    }

    @Test
    void video_tool_has_generate_video_type() {
        ToolDef vid = MediaTools.videoTool("my_video", "Make video", "openai", "sora-2");
        assertEquals("generate_video", vid.getToolType(),
            "videoTool must have toolType='generate_video'");
    }

    @Test
    void pdf_tool_has_generate_pdf_type() {
        ToolDef pdf = MediaTools.pdfTool();
        assertEquals("generate_pdf", pdf.getToolType(),
            "pdfTool must have toolType='generate_pdf'");
    }

    @Test
    void media_tools_serialized_in_agent() {
        ToolDef img = MediaTools.imageTool("img_tool", "image", "openai", "dall-e-3");
        Agent agent = Agent.builder()
            .name("media_agent")
            .model("openai/gpt-4o-mini")
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
            .model("openai/gpt-4o-mini")
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
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .tools(List.of(human))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        assertEquals("human", tool(out, "human_tool").get("toolType"));
    }

    // ── ClaudeCode ────────────────────────────────────────────────────────

    @Test
    void claude_code_model_string_format() {
        ClaudeCode cc = new ClaudeCode("opus");
        assertTrue(cc.toModelString().startsWith("claude-code/"),
            "toModelString() must start with 'claude-code/'");
        assertTrue(cc.toModelString().contains("opus"));
    }

    @Test
    void claude_code_permission_modes() {
        for (ClaudeCode.PermissionMode mode : ClaudeCode.PermissionMode.values()) {
            ClaudeCode cc = new ClaudeCode("sonnet", mode);
            assertNotNull(cc.toModelString());
            assertTrue(cc.toModelString().startsWith("claude-code/"));
        }
    }

    @Test
    void claude_code_model_in_agent_serialized() {
        ClaudeCode cc = new ClaudeCode("sonnet");
        Agent agent = Agent.builder()
            .name("cc_agent")
            .model(cc.toModelString())
            .instructions("test")
            .build();

        Map<String, Object> out = ser.serialize(agent);
        String model = (String) out.get("model");
        assertTrue(model.startsWith("claude-code/"),
            "model in serialized output must start with 'claude-code/'");
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
        Agent agent = GPTAssistantAgent.create("tool_assistant")
            .model("gpt-4o")
            .build();

        Map<String, Object> out = ser.serialize(agent);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) out.get("tools");
        assertNotNull(tools);
        boolean hasCallTool = tools.stream()
            .anyMatch(t -> ((String) t.get("name")).endsWith("_assistant_call"));
        assertTrue(hasCallTool,
            "GPTAssistantAgent must have a '{name}_assistant_call' tool");
    }

    @Test
    void gpt_assistant_normalizes_model_prefix() {
        Agent withPrefix = GPTAssistantAgent.create("a1").model("openai/gpt-4o").build();
        Agent withoutPrefix = GPTAssistantAgent.create("a2").model("gpt-4o").build();

        Map<String, Object> out1 = ser.serialize(withPrefix);
        Map<String, Object> out2 = ser.serialize(withoutPrefix);

        assertEquals("openai/gpt-4o", out1.get("model"));
        assertEquals("openai/gpt-4o", out2.get("model"),
            "model without 'openai/' prefix should be normalized to 'openai/gpt-4o'");
    }

    // ── Skill agent ───────────────────────────────────────────────────────

    @Test
    void skill_agent_uses_framework_fast_path() {
        Agent skillAgent = Agent.builder()
            .name("my_skill")
            .model("openai/gpt-4o-mini")
            .framework("skill")
            .frameworkConfig(Map.of("skillMd", "# My Skill\nDo things."))
            .build();

        Map<String, Object> out = ser.serialize(skillAgent);

        assertEquals("skill", out.get("_framework"),
            "Skill agent must serialize _framework='skill'");
        assertEquals("my_skill", out.get("name"));
        assertNotNull(out.get("skillMd"),
            "frameworkConfig contents should be inlined into the output");
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

    // --- AgentConfig URL normalization ---

    @Test
    void agentConfig_default_url_has_no_api_suffix() {
        AgentConfig cfg = AgentConfig.fromEnv();
        assertFalse(cfg.getServerUrl().endsWith("/api"),
            "Default URL must not end with /api — HttpApi already prepends /api/ to every path");
    }

    @Test
    void agentConfig_strips_trailing_api_from_user_supplied_url() {
        AgentConfig cfg = new AgentConfig("http://localhost:6767/api", null, null, 100, 1);
        assertEquals("http://localhost:6767", cfg.getServerUrl());
    }

    @Test
    void agentConfig_strips_trailing_slash_and_api() {
        AgentConfig cfg = new AgentConfig("http://localhost:6767/api/", null, null, 100, 1);
        assertEquals("http://localhost:6767", cfg.getServerUrl());
    }

    @Test
    void agentConfig_plain_url_unchanged() {
        AgentConfig cfg = new AgentConfig("http://localhost:6767", null, null, 100, 1);
        assertEquals("http://localhost:6767", cfg.getServerUrl());
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

    // ── Retry configuration ───────────────────────────────────────────────

    @Test
    void testSerializeToolWithRetryCount() {
        ToolDef tool = ToolDef.builder()
            .name("retry_tool")
            .description("A tool with retry count")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .retryCount(5)
            .build();

        Agent agent = Agent.builder()
            .name("retry_agent")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .tools(List.of(tool))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> t = tool(out, "retry_tool");
        assertEquals(5, t.get("retryCount"), "retryCount should be 5");
    }

    @Test
    void testSerializeToolWithRetryDelaySeconds() {
        ToolDef tool = ToolDef.builder()
            .name("delay_tool")
            .description("A tool with retry delay")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .retryDelaySeconds(10)
            .build();

        Agent agent = Agent.builder()
            .name("delay_agent")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .tools(List.of(tool))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> t = tool(out, "delay_tool");
        assertEquals(10, t.get("retryDelaySeconds"), "retryDelaySeconds should be 10");
    }

    @Test
    void testSerializeToolWithRetryLogic() {
        ToolDef tool = ToolDef.builder()
            .name("logic_tool")
            .description("A tool with retry logic")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .retryLogic("EXPONENTIAL_BACKOFF")
            .build();

        Agent agent = Agent.builder()
            .name("logic_agent")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .tools(List.of(tool))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> t = tool(out, "logic_tool");
        assertEquals("EXPONENTIAL_BACKOFF", t.get("retryLogic"), "retryLogic should be EXPONENTIAL_BACKOFF");
    }

    @Test
    void testSerializeToolWithAllRetryParams() {
        ToolDef tool = ToolDef.builder()
            .name("all_retry_tool")
            .description("A tool with all retry params")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .retryCount(3)
            .retryDelaySeconds(5)
            .retryLogic("LINEAR_BACKOFF")
            .build();

        Agent agent = Agent.builder()
            .name("all_retry_agent")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .tools(List.of(tool))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> t = tool(out, "all_retry_tool");
        assertEquals(3, t.get("retryCount"), "retryCount should be 3");
        assertEquals(5, t.get("retryDelaySeconds"), "retryDelaySeconds should be 5");
        assertEquals("LINEAR_BACKOFF", t.get("retryLogic"), "retryLogic should be LINEAR_BACKOFF");
    }

    @Test
    void testSerializeToolWithRetryCountZero() {
        ToolDef tool = ToolDef.builder()
            .name("no_retry_tool")
            .description("A tool with no retries")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .retryCount(0)
            .build();

        Agent agent = Agent.builder()
            .name("no_retry_agent")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .tools(List.of(tool))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> t = tool(out, "no_retry_tool");
        assertEquals(0, t.get("retryCount"), "retryCount=0 should be present (fail-immediately)");
    }

    @Test
    void testSerializeToolWithDefaultRetry() {
        ToolDef tool = ToolDef.builder()
            .name("default_retry_tool")
            .description("A tool with default retry settings")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();

        Agent agent = Agent.builder()
            .name("default_retry_agent")
            .model("openai/gpt-4o-mini")
            .instructions("test")
            .tools(List.of(tool))
            .build();

        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> t = tool(out, "default_retry_tool");
        assertNull(t.get("retryCount"), "retryCount should be absent when not set");
        assertNull(t.get("retryDelaySeconds"), "retryDelaySeconds should be absent when not set");
        assertNull(t.get("retryLogic"), "retryLogic should be absent when not set");
    }

    // --- Guardrail (custom / external) ---

    @Test
    @SuppressWarnings("unchecked")
    void guardrail_custom_serialized_as_custom_type() {
        GuardrailDef g = Guardrail.of("no_bad_words", content ->
                GuardrailResult.pass()).build();
        Agent agent = Agent.builder()
                .name("a").model("openai/gpt-4o")
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
        GuardrailDef g = Guardrail.external("corporate_safety").position(Position.INPUT).build();
        Agent agent = Agent.builder()
                .name("a").model("openai/gpt-4o")
                .guardrails(List.of(g))
                .build();
        Map<String, Object> out = ser.serialize(agent);
        Map<String, Object> gMap = guardrail(out, "corporate_safety");
        assertEquals("external", gMap.get("guardrailType"));
        assertEquals("input", gMap.get("position"));
    }
}
