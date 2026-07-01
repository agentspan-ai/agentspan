// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.conductoross.conductor.ai.annotations.AgentDef;
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.enums.Strategy;
import org.conductoross.conductor.ai.model.GuardrailResult;
import org.conductoross.conductor.ai.model.PromptTemplate;
import org.conductoross.conductor.ai.model.ToolDef;
import org.junit.jupiter.api.Test;

/**
 * Tests for {@link AgentDef @AgentDef}-annotated
 * method resolution via {@link Agent#fromInstance(Object)}.
 */
class AgentAnnotationTest {

    // ── Fixtures ─────────────────────────────────────────────────────────

    static class BasicAgent {
        @AgentDef(model = "openai/gpt-4o", instructions = "You are a helpful assistant.")
        public void assistant() {}
    }

    static class DynamicInstructions {
        @AgentDef(model = "openai/gpt-4o", instructions = "static fallback")
        public String weatherbot() {
            return "You are a weather assistant.";
        }
    }

    static class EmptyDynamicInstructions {
        @AgentDef(model = "openai/gpt-4o", instructions = "static fallback")
        public String agentWithFallback() {
            return "";
        }
    }

    static class WithTools {
        @Tool(description = "Get weather for a city")
        public String getWeather(String city) {
            return "Sunny, 72F in " + city;
        }

        @Tool(name = "get_time", description = "Get current time")
        public String getTime() {
            return "12:00";
        }

        @AgentDef(model = "openai/gpt-4o")
        public String allTools() {
            return "You can use all tools.";
        }

        @AgentDef(
                model = "openai/gpt-4o",
                tools = {"get_time"})
        public String oneTool() {
            return "You can tell the time.";
        }

        @AgentDef(
                model = "openai/gpt-4o",
                tools = {})
        public String noTools() {
            return "No tools for you.";
        }
    }

    static class UnknownToolName {
        @Tool(description = "Get weather")
        public String getWeather(String city) {
            return "Sunny";
        }

        @AgentDef(
                model = "openai/gpt-4o",
                tools = {"does_not_exist"})
        public void broken() {}
    }

    static class WithGuardrails {
        @org.conductoross.conductor.ai.annotations.GuardrailDef
        public GuardrailResult noPii(String output) {
            return GuardrailResult.pass();
        }

        @AgentDef(model = "openai/gpt-4o")
        public void guarded() {}

        @AgentDef(
                model = "openai/gpt-4o",
                guardrails = {})
        public void unguarded() {}
    }

    static class MultiAgent {
        @AgentDef(instructions = "Handle billing questions.")
        public void billing() {}

        @AgentDef(model = "anthropic/claude-sonnet-4-6", instructions = "Handle technical support.")
        public void support() {}

        @AgentDef(
                model = "openai/gpt-4o",
                instructions = "Route customer questions.",
                agents = {"billing", "support"},
                strategy = Strategy.HANDOFF)
        public void triage() {}
    }

    static class UnknownSubAgent {
        @AgentDef(
                model = "openai/gpt-4o",
                agents = {"ghost"})
        public void parent() {}
    }

    static class CyclicAgents {
        @AgentDef(
                model = "openai/gpt-4o",
                agents = {"b"})
        public void a() {}

        @AgentDef(
                model = "openai/gpt-4o",
                agents = {"a"})
        public void b() {}
    }

    static class CustomAttributes {
        @AgentDef(
                name = "custom_name",
                model = "openai/gpt-4o",
                maxTurns = 5,
                maxTokens = 1024,
                temperature = 0.2,
                credentials = {"OPENAI_API_KEY"},
                contextWindowBudget = 50000)
        public void ignoredMethodName() {}
    }

    static class BuilderCustomizer {
        @Tool(description = "Search the web")
        public String search(String query) {
            return "results";
        }

        @AgentDef(model = "openai/gpt-4o", instructions = "You are a researcher.")
        public void researcher(Agent.Builder builder) {
            builder.termination(new org.conductoross.conductor.ai.termination.MaxMessageTermination(5))
                    .synthesize(false);
        }

        @AgentDef(model = "openai/gpt-4o", instructions = "static")
        public String dynamicWithCustomizer(Agent.Builder builder) {
            builder.maskedFields("ssn");
            return "dynamic instructions";
        }
    }

    static class StrategyViaCustomizer {
        @AgentDef(instructions = "Write a draft.")
        public void writer() {}

        @AgentDef(
                model = "openai/gpt-4o",
                strategy = Strategy.SEQUENTIAL,
                tools = {})
        public void pipeline(Agent.Builder builder) {
            builder.agents(
                    Agent.fromInstance(this, "writer"), Agent.fromInstance(new CrossClassSpecialist(), "editor"));
        }
    }

    static class CrossClassSpecialist {
        @AgentDef(model = "anthropic/claude-sonnet-4-6", instructions = "Edit the draft.")
        public void editor() {}
    }

    static class TwoParameters {
        @AgentDef(model = "openai/gpt-4o")
        public void bad(Agent.Builder builder, String extra) {}
    }

    static class PromptTemplateReturn {
        @AgentDef(model = "openai/gpt-4o")
        public PromptTemplate templated() {
            return new PromptTemplate("customer-support", Map.of("tone", "friendly"));
        }
    }

    static class FullAgentFactory {
        @AgentDef
        public Agent handbuilt() {
            return Agent.builder()
                    .name("handbuilt")
                    .model("openai/gpt-4o")
                    .instructions("Factory built.")
                    .maxTurns(3)
                    .build();
        }
    }

    static class FluentBuilderReturn {
        @AgentDef(model = "openai/gpt-4o", instructions = "fluent")
        public Agent.Builder fluent(Agent.Builder builder) {
            return builder.maxTurns(3);
        }
    }

    static class NoArgBuilderFactory {
        @AgentDef
        public Agent.Builder scratch() {
            return Agent.builder().name("scratch_agent").model("openai/gpt-4o");
        }
    }

    static class FactoryWithAttributes {
        @AgentDef(model = "openai/gpt-4o")
        public Agent bad() {
            return Agent.builder().name("x").build();
        }
    }

    static class NullFactory {
        @AgentDef
        public Agent nothing() {
            return null;
        }
    }

    static class LazyInstructions {
        int calls = 0;

        @AgentDef(model = "openai/gpt-4o")
        public String counterbot() {
            calls++;
            return "version " + calls;
        }
    }

    static class EagerWithBuilder {
        int calls = 0;

        @AgentDef(model = "openai/gpt-4o")
        public String eager(Agent.Builder builder) {
            calls++;
            return "eager " + calls;
        }
    }

    static class HiddenAgent {
        @AgentDef(model = "openai/gpt-4o")
        private void secret() {}
    }

    static class BaseBot {
        @AgentDef(model = "openai/gpt-4o")
        public String bot() {
            return "base instructions";
        }
    }

    /** Simulates a CGLIB-style proxy: overrides the annotated method without re-annotating. */
    static class ProxyBot extends BaseBot {
        @Override
        public String bot() {
            return "proxied instructions";
        }
    }

    static class PlainChild extends BaseBot {}

    interface BotDefs {
        @AgentDef(model = "openai/gpt-4o", instructions = "From interface.")
        default void ifaceBot() {}
    }

    static class ImplBot implements BotDefs {}

    static class ToolAndAgent {
        @Tool(description = "x")
        @AgentDef(model = "openai/gpt-4o")
        public String both() {
            return "x";
        }
    }

    static class BadReturnType {
        @AgentDef(model = "openai/gpt-4o")
        public int badReturn() {
            return 42;
        }
    }

    static class BadParameters {
        @AgentDef(model = "openai/gpt-4o")
        public String badParams(String unexpected) {
            return "instructions";
        }
    }

    // ── Tests ────────────────────────────────────────────────────────────

    @Test
    void basicAgentUsesMethodNameAndStaticInstructions() {
        List<Agent> agents = Agent.fromInstance(new BasicAgent());
        assertEquals(1, agents.size());
        Agent agent = agents.get(0);
        assertEquals("assistant", agent.getName());
        assertEquals("openai/gpt-4o", agent.getModel());
        assertEquals("You are a helpful assistant.", agent.getInstructions());
        assertEquals(25, agent.getMaxTurns());
    }

    @Test
    void stringReturningMethodProvidesDynamicInstructions() {
        Agent agent = Agent.fromInstance(new DynamicInstructions(), "weatherbot");
        assertEquals("You are a weather assistant.", agent.getInstructions());
    }

    @Test
    void emptyDynamicInstructionsFallBackToAttribute() {
        Agent agent = Agent.fromInstance(new EmptyDynamicInstructions(), "agentWithFallback");
        assertEquals("static fallback", agent.getInstructions());
    }

    @Test
    void allToolMethodsAttachedByDefault() {
        Agent agent = Agent.fromInstance(new WithTools(), "allTools");
        assertEquals(2, agent.getTools().size());
        List<String> names = agent.getTools().stream().map(ToolDef::getName).toList();
        assertTrue(names.contains("getWeather"));
        assertTrue(names.contains("get_time"));
    }

    @Test
    void toolsFilteredByName() {
        Agent agent = Agent.fromInstance(new WithTools(), "oneTool");
        assertEquals(1, agent.getTools().size());
        assertEquals("get_time", agent.getTools().get(0).getName());
    }

    @Test
    void emptyToolsArrayAttachesNoTools() {
        Agent agent = Agent.fromInstance(new WithTools(), "noTools");
        assertTrue(agent.getTools().isEmpty());
    }

    @Test
    void unknownToolNameThrows() {
        IllegalArgumentException e =
                assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new UnknownToolName()));
        assertTrue(e.getMessage().contains("does_not_exist"));
    }

    @Test
    void guardrailsAttachedByDefaultAndFilterable() {
        Agent guarded = Agent.fromInstance(new WithGuardrails(), "guarded");
        assertEquals(1, guarded.getGuardrails().size());
        assertEquals("noPii", guarded.getGuardrails().get(0).getName());

        Agent unguarded = Agent.fromInstance(new WithGuardrails(), "unguarded");
        assertTrue(unguarded.getGuardrails().isEmpty());
    }

    @Test
    void subAgentsResolvedByNameWithModelInheritance() {
        Agent triage = Agent.fromInstance(new MultiAgent(), "triage");
        assertEquals(Strategy.HANDOFF, triage.getStrategy());
        assertEquals(2, triage.getAgents().size());

        Agent billing = triage.getAgents().get(0);
        assertEquals("billing", billing.getName());
        // billing has no model — inherits the parent's
        assertEquals("openai/gpt-4o", billing.getModel());

        Agent support = triage.getAgents().get(1);
        // support declares its own model — no inheritance
        assertEquals("anthropic/claude-sonnet-4-6", support.getModel());
    }

    @Test
    void topLevelResolutionReturnsAllAgents() {
        List<Agent> agents = Agent.fromInstance(new MultiAgent());
        assertEquals(3, agents.size());
    }

    @Test
    void unknownSubAgentNameThrows() {
        IllegalArgumentException e =
                assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new UnknownSubAgent()));
        assertTrue(e.getMessage().contains("ghost"));
    }

    @Test
    void cyclicSubAgentsThrow() {
        assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new CyclicAgents()));
    }

    @Test
    void annotationAttributesMapToAgentFields() {
        Agent agent = Agent.fromInstance(new CustomAttributes(), "custom_name");
        assertEquals("custom_name", agent.getName());
        assertEquals(5, agent.getMaxTurns());
        assertEquals(1024, agent.getMaxTokens());
        assertEquals(0.2, agent.getTemperature());
        assertEquals(List.of("OPENAI_API_KEY"), agent.getCredentials());
        assertEquals(50000, agent.getContextWindowBudget());
    }

    @Test
    void unsetOptionalsStayNull() {
        Agent agent = Agent.fromInstance(new BasicAgent(), "assistant");
        assertNull(agent.getMaxTokens());
        assertNull(agent.getTemperature());
        assertNull(agent.getContextWindowBudget());
    }

    @Test
    void customizerReceivesPrepopulatedBuilder() {
        Agent agent = Agent.fromInstance(new BuilderCustomizer(), "researcher");
        // customizations from the method body
        assertTrue(agent.getTermination() instanceof org.conductoross.conductor.ai.termination.MaxMessageTermination);
        assertTrue(!agent.isSynthesize());
        // pre-populated state from the annotation survives
        assertEquals("openai/gpt-4o", agent.getModel());
        assertEquals("You are a researcher.", agent.getInstructions());
        assertEquals(1, agent.getTools().size());
        assertEquals("search", agent.getTools().get(0).getName());
    }

    @Test
    void returnedStringWinsOverCustomizerAndAttribute() {
        Agent agent = Agent.fromInstance(new BuilderCustomizer(), "dynamicWithCustomizer");
        assertEquals("dynamic instructions", agent.getInstructions());
        assertEquals(List.of("ssn"), agent.getMaskedFields());
    }

    @Test
    void strategyAppliesWhenSubAgentsAddedViaCustomizer() {
        Agent pipeline = Agent.fromInstance(new StrategyViaCustomizer(), "pipeline");
        assertEquals(Strategy.SEQUENTIAL, pipeline.getStrategy());
        assertEquals(2, pipeline.getAgents().size());
        // cross-class sub-agent resolved from another instance
        assertEquals("editor", pipeline.getAgents().get(1).getName());
        assertEquals("anthropic/claude-sonnet-4-6", pipeline.getAgents().get(1).getModel());
    }

    @Test
    void extraParametersBeyondBuilderThrow() {
        assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new TwoParameters()));
    }

    // ── Return-type ladder ───────────────────────────────────────────────

    @Test
    void promptTemplateReturnSetsInstructionsTemplate() {
        Agent agent = Agent.fromInstance(new PromptTemplateReturn(), "templated");
        assertEquals("customer-support", agent.getInstructionsTemplate().getName());
        assertEquals("friendly", agent.getInstructionsTemplate().getVariables().get("tone"));
    }

    @Test
    void agentReturningMethodIsFullFactory() {
        // discovery key is the method name; the agent keeps the name set by the factory
        Agent agent = Agent.fromInstance(new FullAgentFactory(), "handbuilt");
        assertEquals("handbuilt", agent.getName());
        assertEquals("Factory built.", agent.getInstructions());
        assertEquals(3, agent.getMaxTurns());
    }

    @Test
    void returnedBuilderIsBuiltWithAnnotationDefaults() {
        Agent agent = Agent.fromInstance(new FluentBuilderReturn(), "fluent");
        assertEquals(3, agent.getMaxTurns());
        assertEquals("openai/gpt-4o", agent.getModel());
        assertEquals("fluent", agent.getInstructions());
    }

    @Test
    void noArgBuilderReturnIsFactoryBuiltAsIs() {
        Agent agent = Agent.fromInstance(new NoArgBuilderFactory(), "scratch");
        assertEquals("scratch_agent", agent.getName());
        assertEquals("openai/gpt-4o", agent.getModel());
    }

    @Test
    void pureFactoryWithNonDefaultAttributesThrows() {
        IllegalArgumentException e =
                assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new FactoryWithAttributes()));
        assertTrue(e.getMessage().contains("model"));
    }

    @Test
    void factoryReturningNullThrows() {
        assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new NullFactory()));
    }

    // ── Lazy instructions (evaluated per access, i.e. per run submission) ─

    @Test
    void noArgStringInstructionsAreLazyAndReevaluated() {
        LazyInstructions fixture = new LazyInstructions();
        Agent agent = Agent.fromInstance(fixture, "counterbot");
        assertEquals(0, fixture.calls);
        assertEquals("version 1", agent.getInstructions());
        assertEquals("version 2", agent.getInstructions());
        assertEquals(2, fixture.calls);
    }

    @Test
    void supplierInstructionsOnBuilderAreReevaluatedPerAccess() {
        AtomicInteger calls = new AtomicInteger();
        Agent agent = Agent.builder()
                .name("lazy")
                .model("openai/gpt-4o")
                .instructions(() -> "prompt v" + calls.incrementAndGet())
                .build();
        assertEquals("prompt v1", agent.getInstructions());
        assertEquals("prompt v2", agent.getInstructions());
    }

    @Test
    void lazyInstructionsReachTheSerializedConfig() {
        LazyInstructions fixture = new LazyInstructions();
        Agent agent = Agent.fromInstance(fixture, "counterbot");
        var serializer = new org.conductoross.conductor.ai.internal.AgentConfigSerializer();
        assertEquals("version 1", serializer.serialize(agent).get("instructions"));
        assertEquals("version 2", serializer.serialize(agent).get("instructions"));
    }

    @Test
    void builderParamStringInstructionsStayEager() {
        EagerWithBuilder fixture = new EagerWithBuilder();
        Agent agent = Agent.fromInstance(fixture, "eager");
        assertEquals(1, fixture.calls);
        assertEquals("eager 1", agent.getInstructions());
        assertEquals("eager 1", agent.getInstructions());
        assertEquals(1, fixture.calls);
    }

    // ── Discovery: visibility, inheritance, proxies ──────────────────────

    @Test
    void nonPublicAgentDefMethodThrowsInsteadOfSilentIgnore() {
        IllegalArgumentException e =
                assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new HiddenAgent()));
        assertTrue(e.getMessage().contains("public"));
        assertTrue(e.getMessage().contains("secret"));
    }

    @Test
    void unannotatedOverrideStillDiscoveredWithVirtualDispatch() {
        // a subclass (e.g. CGLIB proxy) overriding without re-annotating must not
        // hide the agent, and invocation must dispatch to the override
        Agent agent = Agent.fromInstance(new ProxyBot(), "bot");
        assertEquals("proxied instructions", agent.getInstructions());
    }

    @Test
    void inheritedAnnotatedMethodDiscovered() {
        assertEquals(
                "base instructions", Agent.fromInstance(new PlainChild(), "bot").getInstructions());
        assertEquals(
                "base instructions", Agent.fromInstance(new BaseBot(), "bot").getInstructions());
    }

    @Test
    void interfaceDefaultMethodDiscovered() {
        Agent agent = Agent.fromInstance(new ImplBot(), "ifaceBot");
        assertEquals("From interface.", agent.getInstructions());
    }

    @Test
    void agentDefCombinedWithToolThrows() {
        IllegalArgumentException e =
                assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new ToolAndAgent()));
        assertTrue(e.getMessage().contains("@Tool"));
    }

    @Test
    void nonStringNonVoidReturnTypeThrows() {
        assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new BadReturnType()));
    }

    @Test
    void stringReturningMethodWithParametersThrows() {
        assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new BadParameters()));
    }

    @Test
    void missingNamedAgentThrows() {
        IllegalArgumentException e =
                assertThrows(IllegalArgumentException.class, () -> Agent.fromInstance(new BasicAgent(), "nope"));
        assertTrue(e.getMessage().contains("nope"));
    }
}
