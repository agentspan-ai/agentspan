// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.conductoross.conductor.ai.enums.Strategy;

/**
 * Marks a method as an agent definition.
 *
 * <p>The Java counterpart of the Python SDK's {@code @agent} decorator. Annotate a
 * method to define an agent declaratively; resolve it into an
 * {@link org.conductoross.conductor.ai.Agent} with
 * {@link org.conductoross.conductor.ai.Agent#fromInstance(Object)} or
 * {@link org.conductoross.conductor.ai.Agent#fromInstance(Object, String)}.
 *
 * <p>The method's <em>return type declares what it provides</em>:
 * <ul>
 *   <li>{@code void} — nothing; the annotation attributes alone define the agent.</li>
 *   <li>{@code String} — dynamic instructions. A no-arg method is <em>lazy</em>: it is
 *       re-invoked every time the agent config is serialized (each run submission),
 *       so the prompt can reflect current state — matching the Python SDK, where
 *       callable instructions resolve at serialization time. A non-empty result wins
 *       over the {@link #instructions()} attribute.</li>
 *   <li>{@code PromptTemplate} — a server-side instructions template
 *       (sets {@code instructionsTemplate}); invoked once.</li>
 *   <li>{@code Agent.Builder} — the definition itself; the returned builder is built.</li>
 *   <li>{@code Agent} — the definition itself, returned as-is (CrewAI-style full
 *       factory). For no-arg factory forms, annotation attributes other than
 *       {@link #name()} are rejected — they would be silently ignored.</li>
 * </ul>
 *
 * <p>The method may take no parameters, or a single
 * {@link org.conductoross.conductor.ai.Agent.Builder Agent.Builder} parameter as an
 * escape hatch: the builder arrives pre-populated from the annotation (and the
 * discovered tools/guardrails/sub-agents), and the method body can apply anything
 * the builder supports — termination conditions, handoffs, memory, sub-agents from
 * other classes, etc. Builder-param methods are invoked exactly once (re-running a
 * customizer per serialization would replay its side effects).
 *
 * <p>{@link Tool} and {@link GuardrailDef} methods declared on the same object are
 * attached to the agent automatically (all of them by default — see {@link #tools()}
 * and {@link #guardrails()}). Sub-agents are referenced by name via {@link #agents()}.
 *
 * <p>Example:
 * <pre>{@code
 * public class Weather {
 *     @Tool(description = "Get weather for a city")
 *     public String getWeather(String city) { return "Sunny, 72F in " + city; }
 *
 *     @AgentDef(model = "openai/gpt-4o")
 *     public String weatherbot() {
 *         return "You are a weather assistant. Today is " + LocalDate.now() + ".";
 *     }
 *
 *     // builder customizer: full builder API available
 *     @AgentDef(model = "openai/gpt-4o", instructions = "You are a researcher.")
 *     public void researcher(Agent.Builder builder) {
 *         builder.termination(new MaxMessageTermination(10))
 *                .agents(Agent.fromInstance(new Editing(), "editor"));
 *     }
 *
 *     // full factory: the method builds the whole definition
 *     @AgentDef
 *     public Agent reviewer() {
 *         return Agent.builder().name("reviewer").model("openai/gpt-4o")
 *                 .instructions("Review the draft.").build();
 *     }
 * }
 *
 * Agent agent = Agent.fromInstance(new Weather(), "weatherbot");
 * }</pre>
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AgentDef {
    /** Agent name. Defaults to the method name if not specified. */
    String name() default "";

    /**
     * LLM model in "provider/model" format (e.g. "openai/gpt-4o").
     * When empty and this agent is referenced as a sub-agent, the parent's
     * model is inherited at resolution time.
     */
    String model() default "";

    /**
     * Static system prompt. A non-empty {@code String} returned by the annotated
     * method takes precedence over this attribute.
     */
    String instructions() default "";

    /**
     * Names of {@link Tool}-annotated methods on the same object to attach.
     * The default {@code {"*"}} attaches all of them; an empty array attaches none.
     */
    String[] tools() default {"*"};

    /**
     * Names of {@link GuardrailDef}-annotated methods on the same object to attach.
     * The default {@code {"*"}} attaches all of them; an empty array attaches none.
     */
    String[] guardrails() default {"*"};

    /**
     * Names of other {@code @AgentDef}-annotated methods on the same object to use
     * as sub-agents for multi-agent orchestration.
     */
    String[] agents() default {};

    /** Multi-agent orchestration strategy. Only meaningful when {@link #agents()} is set. */
    Strategy strategy() default Strategy.HANDOFF;

    /** Maximum number of agent loop iterations. */
    int maxTurns() default 25;

    /** Maximum tokens for LLM generation. 0 means unset (server default applies). */
    int maxTokens() default 0;

    /** Sampling temperature. NaN means unset (server default applies). */
    double temperature() default Double.NaN;

    /** Agent-level credential names to inject into the execution context. */
    String[] credentials() default {};

    /** Token budget for proactive context condensation. 0 means unset. */
    int contextWindowBudget() default 0;
}
