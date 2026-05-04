// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.e2e;

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.ClaudeCode;
import ai.agentspan.UserProxyAgent;
import ai.agentspan.enums.OnFail;
import ai.agentspan.enums.Position;
import ai.agentspan.enums.Strategy;
import ai.agentspan.gate.TextGate;
import ai.agentspan.guardrail.LLMGuardrail;
import ai.agentspan.guardrail.RegexGuardrail;
import ai.agentspan.handoff.OnCondition;
import ai.agentspan.model.DeploymentInfo;
import ai.agentspan.model.GuardrailDef;
import ai.agentspan.model.ToolDef;
import ai.agentspan.openai.GPTAssistantAgent;
import ai.agentspan.termination.StopMessageTermination;
import ai.agentspan.tools.HumanTool;
import ai.agentspan.tools.MediaTools;
import ai.agentspan.tools.WaitForMessageTool;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 11: New parity features — structural plan() assertions.
 *
 * <p>Tests the features added for Python parity:
 * stateful, baseUrl, TextGate, before/after_agent callbacks, StopMessageTermination,
 * RegexGuardrail, LLMGuardrail, OnCondition handoff, UserProxyAgent, ClaudeCode model,
 * MediaTools, WaitForMessageTool, HumanTool, GPTAssistantAgent, deploy().
 *
 * <p>All tests use plan() — no LLM calls. COUNTERFACTUAL: each test is designed to
 * fail if the corresponding feature serializes incorrectly.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class E2eSuite11NewParity extends E2eBaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new ai.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Helper ────────────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private Map<String, Object> findToolByName(Map<String, Object> agentDef, String name) {
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef has no 'tools' key");
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
    private Map<String, Object> findGuardrailByName(Map<String, Object> agentDef, String name) {
        List<Map<String, Object>> guardrails = (List<Map<String, Object>>) agentDef.get("guardrails");
        assertNotNull(guardrails, "agentDef has no 'guardrails' key");
        return guardrails.stream()
            .filter(g -> name.equals(g.get("name")))
            .findFirst()
            .orElseGet(() -> {
                fail("Guardrail '" + name + "' not found. Available: "
                    + guardrails.stream().map(g -> (String) g.get("name")).collect(Collectors.toList()));
                return null;
            });
    }

    // ── Tests ─────────────────────────────────────────────────────────────

    /**
     * stateful=true propagates stateful:true to each tool (mirrors Python SDK behaviour).
     *
     * COUNTERFACTUAL: if stateful is not propagated, worker domain isolation won't be set up.
     */
    @Test
    @Order(1)
    @SuppressWarnings("unchecked")
    void test_stateful_field_serialized() {
        ToolDef workerTool = ToolDef.builder()
            .name("e2e_java_stateful_tool")
            .description("A worker tool.")
            .inputSchema(Map.of("type", "object", "properties", Map.of()))
            .toolType("worker")
            .func(input -> input)
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_stateful")
            .model(MODEL)
            .instructions("A stateful agent.")
            .stateful(true)
            .tools(List.of(workerTool))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef.tools is null");

        Map<String, Object> tool = tools.stream()
            .filter(t -> "e2e_java_stateful_tool".equals(t.get("name")))
            .findFirst()
            .orElseGet(() -> { fail("Tool 'e2e_java_stateful_tool' not found"); return null; });

        assertEquals(Boolean.TRUE, tool.get("stateful"),
            "tool.stateful should be true for a stateful agent but got: " + tool.get("stateful")
            + ". COUNTERFACTUAL: Agent.stateful(true) must propagate stateful=true to each tool.");
    }

    /**
     * baseUrl serializes to agentDef.baseUrl.
     *
     * COUNTERFACTUAL: if baseUrl is not serialized, field will be absent.
     */
    @Test
    @Order(2)
    void test_base_url_serialized() {
        Agent agent = Agent.builder()
            .name("e2e_java_baseurl")
            .model(MODEL)
            .instructions("Agent with custom base URL.")
            .baseUrl("http://my-llm-proxy.internal/v1")
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        assertEquals("http://my-llm-proxy.internal/v1", agentDef.get("baseUrl"),
            "agentDef.baseUrl should be 'http://my-llm-proxy.internal/v1' but got: "
            + agentDef.get("baseUrl")
            + ". COUNTERFACTUAL: Agent.baseUrl() must serialize to agentDef.baseUrl.");
    }

    /**
     * TextGate serializes to agentDef.gate with type/text/caseSensitive fields.
     *
     * COUNTERFACTUAL: if gate is not serialized, the sequential pipeline won't stop.
     */
    @Test
    @Order(3)
    @SuppressWarnings("unchecked")
    void test_text_gate_serialized() {
        Agent checker = Agent.builder()
            .name("e2e_java_gate_checker")
            .model(MODEL)
            .instructions("Check output.")
            .gate(new TextGate("STOP", false))
            .build();

        Map<String, Object> plan = runtime.plan(checker);
        Map<String, Object> agentDef = getAgentDef(plan);

        assertNotNull(agentDef.get("gate"),
            "agentDef.gate is null. COUNTERFACTUAL: TextGate must serialize to agentDef.gate.");

        Map<String, Object> gate = (Map<String, Object>) agentDef.get("gate");
        assertEquals("text_contains", gate.get("type"),
            "gate.type should be 'text_contains' but got: " + gate.get("type"));
        assertEquals("STOP", gate.get("text"),
            "gate.text should be 'STOP' but got: " + gate.get("text"));
        assertEquals(false, gate.get("caseSensitive"),
            "gate.caseSensitive should be false but got: " + gate.get("caseSensitive"));
    }

    /**
     * before_agent_callback serializes to agentDef.callbacks with position "before_agent".
     *
     * COUNTERFACTUAL: if callback is not serialized, it won't fire during execution.
     */
    @Test
    @Order(4)
    @SuppressWarnings("unchecked")
    void test_before_agent_callback_serialized() {
        Agent agent = Agent.builder()
            .name("e2e_java_before_cb")
            .model(MODEL)
            .instructions("Agent with before callback.")
            .beforeAgentCallback(ctx -> ctx)
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) agentDef.get("callbacks");
        assertNotNull(callbacks,
            "agentDef.callbacks is null. COUNTERFACTUAL: beforeAgentCallback must produce agentDef.callbacks.");
        assertFalse(callbacks.isEmpty(),
            "agentDef.callbacks is empty.");

        boolean hasBeforeAgent = callbacks.stream()
            .anyMatch(cb -> "before_agent".equals(cb.get("position")));
        assertTrue(hasBeforeAgent,
            "No callback with position 'before_agent' found. Callbacks: " + callbacks
            + ". COUNTERFACTUAL: beforeAgentCallback must produce position='before_agent'.");
    }

    /**
     * after_agent_callback serializes to agentDef.callbacks with position "after_agent".
     *
     * COUNTERFACTUAL: if callback is not serialized, it won't fire during execution.
     */
    @Test
    @Order(5)
    @SuppressWarnings("unchecked")
    void test_after_agent_callback_serialized() {
        Agent agent = Agent.builder()
            .name("e2e_java_after_cb")
            .model(MODEL)
            .instructions("Agent with after callback.")
            .afterAgentCallback(ctx -> ctx)
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) agentDef.get("callbacks");
        assertNotNull(callbacks,
            "agentDef.callbacks is null. COUNTERFACTUAL: afterAgentCallback must produce agentDef.callbacks.");

        boolean hasAfterAgent = callbacks.stream()
            .anyMatch(cb -> "after_agent".equals(cb.get("position")));
        assertTrue(hasAfterAgent,
            "No callback with position 'after_agent' found. Callbacks: " + callbacks
            + ". COUNTERFACTUAL: afterAgentCallback must produce position='after_agent'.");
    }

    /**
     * StopMessageTermination serializes to agentDef.termination with type "stop_message".
     *
     * COUNTERFACTUAL: if not serialized, the termination condition won't stop the agent.
     */
    @Test
    @Order(6)
    @SuppressWarnings("unchecked")
    void test_stop_message_termination_serialized() {
        Agent agent = Agent.builder()
            .name("e2e_java_stop_msg_term")
            .model(MODEL)
            .instructions("Stop when you output DONE.")
            .termination(StopMessageTermination.of("DONE"))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        assertNotNull(agentDef.get("termination"),
            "agentDef.termination is null. COUNTERFACTUAL: StopMessageTermination must serialize.");

        Map<String, Object> term = (Map<String, Object>) agentDef.get("termination");
        assertEquals("stop_message", term.get("type"),
            "termination.type should be 'stop_message' but got: " + term.get("type")
            + ". COUNTERFACTUAL: StopMessageTermination.of() must produce type='stop_message'.");
        assertEquals("DONE", term.get("stopMessage"),
            "termination.stopMessage should be 'DONE' but got: " + term.get("stopMessage"));
    }

    /**
     * RegexGuardrail serializes to a guardrail with guardrailType "regex" and patterns.
     *
     * COUNTERFACTUAL: if guardrailType is wrong, the server won't evaluate it as regex.
     */
    @Test
    @Order(7)
    @SuppressWarnings("unchecked")
    void test_regex_guardrail_serialized() {
        GuardrailDef guard = RegexGuardrail.builder()
            .name("e2e_java_regex_guard")
            .patterns("[\\w.+-]+@[\\w-]+\\.[\\w.-]+")
            .message("No emails allowed.")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_regex_guard_agent")
            .model(MODEL)
            .instructions("Be helpful.")
            .guardrails(List.of(guard))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);
        Map<String, Object> g = findGuardrailByName(agentDef, "e2e_java_regex_guard");

        assertEquals("regex", g.get("guardrailType"),
            "guardrailType should be 'regex' but got: " + g.get("guardrailType")
            + ". COUNTERFACTUAL: RegexGuardrail.builder().build() must produce guardrailType='regex'.");
        assertEquals("output", g.get("position"),
            "guardrail position should be 'output' but got: " + g.get("position"));

        // patterns and mode are inlined at the top level of the guardrail map (not nested under config)
        assertNotNull(g.get("patterns"),
            "guardrail.patterns is null. COUNTERFACTUAL: RegexGuardrail patterns must serialize at top level.");
    }

    /**
     * LLMGuardrail serializes to a guardrail with guardrailType "llm", model, and policy.
     *
     * COUNTERFACTUAL: if guardrailType is wrong, the server won't call an LLM to evaluate.
     */
    @Test
    @Order(8)
    @SuppressWarnings("unchecked")
    void test_llm_guardrail_serialized() {
        GuardrailDef guard = LLMGuardrail.builder()
            .name("e2e_java_llm_guard")
            .model("openai/gpt-4o-mini")
            .policy("Reject any harmful content.")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .build();

        Agent agent = Agent.builder()
            .name("e2e_java_llm_guard_agent")
            .model(MODEL)
            .instructions("Be helpful.")
            .guardrails(List.of(guard))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);
        Map<String, Object> g = findGuardrailByName(agentDef, "e2e_java_llm_guard");

        assertEquals("llm", g.get("guardrailType"),
            "guardrailType should be 'llm' but got: " + g.get("guardrailType")
            + ". COUNTERFACTUAL: LLMGuardrail.builder().build() must produce guardrailType='llm'.");

        // model and policy are inlined at the top level of the guardrail map (not nested under config)
        assertEquals("openai/gpt-4o-mini", g.get("model"),
            "guardrail.model should be 'openai/gpt-4o-mini' but got: " + g.get("model")
            + ". COUNTERFACTUAL: LLMGuardrail model must serialize at top level of guardrail map.");
        assertEquals("Reject any harmful content.", g.get("policy"),
            "guardrail.policy mismatch. Got: " + g.get("policy"));
    }

    /**
     * OnCondition handoff serializes to agentDef.handoffs with the target agent.
     *
     * COUNTERFACTUAL: if handoff is not serialized, the condition-based routing won't work.
     */
    @Test
    @Order(9)
    @SuppressWarnings("unchecked")
    void test_on_condition_handoff_serialized() {
        Agent supervisor = Agent.builder()
            .name("e2e_java_supervisor")
            .model(MODEL)
            .instructions("Supervisor.")
            .build();

        Agent worker = Agent.builder()
            .name("e2e_java_on_condition_worker")
            .model(MODEL)
            .instructions("Worker that may escalate.")
            .handoffs(List.of(new OnCondition("e2e_java_supervisor",
                ctx -> Boolean.TRUE.equals(ctx.get("escalate")))))
            .build();

        Agent team = Agent.builder()
            .name("e2e_java_on_condition_team")
            .model(MODEL)
            .instructions("Coordinate agents.")
            .agents(supervisor, worker)
            .strategy(Strategy.HANDOFF)
            .build();

        Map<String, Object> plan = runtime.plan(team);
        Map<String, Object> agentDef = getAgentDef(plan);

        // Navigate to the worker sub-agent in the plan
        List<Map<String, Object>> agents = (List<Map<String, Object>>) agentDef.get("agents");
        assertNotNull(agents, "agentDef has no 'agents' key");

        Map<String, Object> workerDef = agents.stream()
            .filter(a -> "e2e_java_on_condition_worker".equals(a.get("name")))
            .findFirst()
            .orElseGet(() -> {
                fail("Worker sub-agent not found in plan agents: "
                    + agents.stream().map(a -> (String) a.get("name")).collect(Collectors.toList()));
                return null;
            });

        List<Map<String, Object>> handoffs = (List<Map<String, Object>>) workerDef.get("handoffs");
        assertNotNull(handoffs,
            "Worker sub-agent has no 'handoffs' key. COUNTERFACTUAL: OnCondition must serialize.");
        assertFalse(handoffs.isEmpty(), "Worker handoffs list is empty.");

        boolean hasSupervisor = handoffs.stream()
            .anyMatch(h -> "e2e_java_supervisor".equals(h.get("target")));
        assertTrue(hasSupervisor,
            "No handoff to 'e2e_java_supervisor' found. Handoffs: " + handoffs
            + ". COUNTERFACTUAL: OnCondition target must appear in handoffs.");
    }

    /**
     * UserProxyAgent creates an agent with metadata _agent_type == "user_proxy".
     *
     * COUNTERFACTUAL: if metadata is missing, the server won't treat it as a human proxy.
     */
    @Test
    @Order(10)
    @SuppressWarnings("unchecked")
    void test_user_proxy_agent_metadata_serialized() {
        Agent user = UserProxyAgent.create("e2e_java_user_proxy", "ALWAYS", "Continue.", MODEL);
        Agent assistant = Agent.builder()
            .name("e2e_java_proxy_assistant")
            .model(MODEL)
            .instructions("Assist the user.")
            .build();
        Agent team = Agent.builder()
            .name("e2e_java_proxy_team")
            .model(MODEL)
            .instructions("Coordinate.")
            .agents(user, assistant)
            .strategy(Strategy.ROUND_ROBIN)
            .build();

        Map<String, Object> plan = runtime.plan(team);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> agents = (List<Map<String, Object>>) agentDef.get("agents");
        assertNotNull(agents, "agentDef has no 'agents'");

        Map<String, Object> userDef = agents.stream()
            .filter(a -> "e2e_java_user_proxy".equals(a.get("name")))
            .findFirst()
            .orElseGet(() -> {
                fail("UserProxyAgent not found in agents: "
                    + agents.stream().map(a -> (String) a.get("name")).collect(Collectors.toList()));
                return null;
            });

        Map<String, Object> metadata = (Map<String, Object>) userDef.get("metadata");
        assertNotNull(metadata,
            "UserProxyAgent has no 'metadata'. COUNTERFACTUAL: UserProxyAgent must set _agent_type.");
        assertEquals("user_proxy", metadata.get("_agent_type"),
            "_agent_type should be 'user_proxy' but got: " + metadata.get("_agent_type")
            + ". COUNTERFACTUAL: UserProxyAgent must set metadata._agent_type='user_proxy'.");
        assertEquals("ALWAYS", metadata.get("_human_input_mode"),
            "_human_input_mode should be 'ALWAYS' but got: " + metadata.get("_human_input_mode"));
    }

    /**
     * MediaTools (imageTool) serializes with toolType "image".
     *
     * COUNTERFACTUAL: if toolType is wrong, the server won't handle media correctly.
     */
    @Test
    @Order(11)
    void test_media_tools_serialized() {
        ToolDef imageTool = MediaTools.imageTool("e2e_java_image_tool", "Analyze an image",
            "imageUrl", "URL of the image to analyze");
        ToolDef audioTool = MediaTools.audioTool("e2e_java_audio_tool", "Transcribe audio",
            "audioUrl", "URL of the audio to transcribe");

        Agent agent = Agent.builder()
            .name("e2e_java_media_agent")
            .model(MODEL)
            .instructions("Process media.")
            .tools(List.of(imageTool, audioTool))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> img = findToolByName(agentDef, "e2e_java_image_tool");
        assertEquals("generate_image", img.get("toolType"),
            "imageTool toolType should be 'generate_image' but got: " + img.get("toolType")
            + ". COUNTERFACTUAL: MediaTools.imageTool() must serialize toolType='generate_image'.");

        Map<String, Object> aud = findToolByName(agentDef, "e2e_java_audio_tool");
        assertEquals("generate_audio", aud.get("toolType"),
            "audioTool toolType should be 'generate_audio' but got: " + aud.get("toolType")
            + ". COUNTERFACTUAL: MediaTools.audioTool() must serialize toolType='generate_audio'.");
    }

    /**
     * WaitForMessageTool serializes with toolType "pull_workflow_messages".
     *
     * COUNTERFACTUAL: wrong toolType means agent won't pause for messages.
     */
    @Test
    @Order(12)
    void test_wait_for_message_tool_serialized() {
        ToolDef waitTool = WaitForMessageTool.create("e2e_java_wait_msg",
            "Wait for incoming messages", 3, true);

        Agent agent = Agent.builder()
            .name("e2e_java_wait_msg_agent")
            .model(MODEL)
            .instructions("Wait for messages.")
            .tools(List.of(waitTool))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> tool = findToolByName(agentDef, "e2e_java_wait_msg");
        assertEquals("pull_workflow_messages", tool.get("toolType"),
            "WaitForMessageTool toolType should be 'pull_workflow_messages' but got: " + tool.get("toolType")
            + ". COUNTERFACTUAL: WaitForMessageTool must serialize toolType='pull_workflow_messages'.");
    }

    /**
     * HumanTool serializes with toolType "human".
     *
     * COUNTERFACTUAL: wrong toolType means the human-in-the-loop pause won't trigger.
     */
    @Test
    @Order(13)
    void test_human_tool_serialized() {
        ToolDef humanTool = HumanTool.create("e2e_java_human_tool", "Ask a human for input.");

        Agent agent = Agent.builder()
            .name("e2e_java_human_tool_agent")
            .model(MODEL)
            .instructions("Pause for human input when needed.")
            .tools(List.of(humanTool))
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> tool = findToolByName(agentDef, "e2e_java_human_tool");
        assertEquals("human", tool.get("toolType"),
            "HumanTool toolType should be 'human' but got: " + tool.get("toolType")
            + ". COUNTERFACTUAL: HumanTool must serialize toolType='human'.");
    }

    /**
     * ClaudeCode model string produces "claude-code/{model}" format.
     *
     * COUNTERFACTUAL: if the model string is wrong, the agent runs on the wrong LLM.
     */
    @Test
    @Order(14)
    void test_claude_code_model_string() {
        ClaudeCode cc = new ClaudeCode("opus", ClaudeCode.PermissionMode.ACCEPT_EDITS);

        String modelString = cc.toModelString();
        assertTrue(modelString.startsWith("claude-code/"),
            "ClaudeCode model string should start with 'claude-code/' but got: " + modelString
            + ". COUNTERFACTUAL: ClaudeCode.toModelString() must return 'claude-code/{model}'.");
        assertTrue(modelString.contains("opus"),
            "ClaudeCode model string should contain 'opus' but got: " + modelString);
    }

    /**
     * ClaudeCode agent serializes with the correct model string in agentDef.model.
     *
     * COUNTERFACTUAL: if not serialized correctly, server uses a different LLM.
     */
    @Test
    @Order(15)
    void test_claude_code_agent_plan() {
        ClaudeCode cc = new ClaudeCode("sonnet");
        Agent agent = Agent.builder()
            .name("e2e_java_claude_code_agent")
            .model(cc.toModelString())
            .instructions("Use Claude Code.")
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        String model = (String) agentDef.get("model");
        assertTrue(model != null && model.startsWith("claude-code/"),
            "agentDef.model should start with 'claude-code/' but got: " + model
            + ". COUNTERFACTUAL: ClaudeCode.toModelString() in Agent.model() must be preserved.");
    }

    /**
     * GPTAssistantAgent.create().build() returns an Agent with metadata _agent_type="gpt_assistant".
     *
     * COUNTERFACTUAL: if metadata is missing, the server doesn't know it's a GPT assistant.
     */
    @Test
    @Order(16)
    @SuppressWarnings("unchecked")
    void test_gpt_assistant_agent_metadata_serialized() {
        Agent agent = GPTAssistantAgent.create("e2e_java_gpt_assistant")
            .model("gpt-4o")
            .instructions("You are a data analyst.")
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        Map<String, Object> metadata = (Map<String, Object>) agentDef.get("metadata");
        assertNotNull(metadata,
            "agentDef.metadata is null. COUNTERFACTUAL: GPTAssistantAgent must set _agent_type in metadata.");
        assertEquals("gpt_assistant", metadata.get("_agent_type"),
            "_agent_type should be 'gpt_assistant' but got: " + metadata.get("_agent_type")
            + ". COUNTERFACTUAL: GPTAssistantAgent.create().build() must set metadata._agent_type='gpt_assistant'.");

        // The agent should have a call tool registered
        List<Map<String, Object>> tools = (List<Map<String, Object>>) agentDef.get("tools");
        assertNotNull(tools, "agentDef.tools is null");
        boolean hasCallTool = tools.stream()
            .anyMatch(t -> ((String) t.get("name")).endsWith("_assistant_call"));
        assertTrue(hasCallTool,
            "GPTAssistantAgent should have a '{name}_assistant_call' tool. Tools: "
            + tools.stream().map(t -> (String) t.get("name")).collect(Collectors.toList()));
    }

    /**
     * deploy() pushes agent to the server and returns DeploymentInfo without error.
     *
     * COUNTERFACTUAL: if deploy() throws, the test fails; if it returns null registeredName, the assertion fails.
     */
    @Test
    @Order(17)
    void test_deploy_returns_deployment_info() {
        Agent agent = Agent.builder()
            .name("e2e_java_deploy_target")
            .model(MODEL)
            .instructions("A deployable agent.")
            .build();

        List<DeploymentInfo> results = runtime.deploy(agent);

        assertNotNull(results,
            "deploy() returned null. COUNTERFACTUAL: deploy() must return a non-null list.");
        assertFalse(results.isEmpty(),
            "deploy() returned empty list. COUNTERFACTUAL: deploy() must return one DeploymentInfo per agent.");

        DeploymentInfo info = results.get(0);
        assertNotNull(info.getRegisteredName(),
            "DeploymentInfo.registeredName is null. COUNTERFACTUAL: server must return the registered agent name.");
        assertFalse(info.getRegisteredName().isEmpty(),
            "DeploymentInfo.registeredName is empty.");
        assertEquals("e2e_java_deploy_target", info.getAgentName(),
            "DeploymentInfo.agentName should be 'e2e_java_deploy_target' but got: " + info.getAgentName());
    }

    /**
     * Both before and after callbacks serialize together when both are set.
     *
     * COUNTERFACTUAL: if only one is serialized, execution will miss one callback.
     */
    @Test
    @Order(18)
    @SuppressWarnings("unchecked")
    void test_both_agent_callbacks_serialized() {
        Agent agent = Agent.builder()
            .name("e2e_java_both_callbacks")
            .model(MODEL)
            .instructions("Agent with both callbacks.")
            .beforeAgentCallback(ctx -> ctx)
            .afterAgentCallback(ctx -> ctx)
            .build();

        Map<String, Object> plan = runtime.plan(agent);
        Map<String, Object> agentDef = getAgentDef(plan);

        List<Map<String, Object>> callbacks = (List<Map<String, Object>>) agentDef.get("callbacks");
        assertNotNull(callbacks, "agentDef.callbacks is null.");
        assertEquals(2, callbacks.size(),
            "Should have 2 callbacks (before + after) but got " + callbacks.size()
            + ". Callbacks: " + callbacks
            + ". COUNTERFACTUAL: both before and after agent callbacks must serialize.");

        boolean hasBefore = callbacks.stream().anyMatch(cb -> "before_agent".equals(cb.get("position")));
        boolean hasAfter = callbacks.stream().anyMatch(cb -> "after_agent".equals(cb.get("position")));
        assertTrue(hasBefore, "No 'before_agent' callback found among: " + callbacks);
        assertTrue(hasAfter, "No 'after_agent' callback found among: " + callbacks);
    }
}
