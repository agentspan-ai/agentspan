// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.annotations.AgentDef;
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.enums.Strategy;
import org.conductoross.conductor.ai.model.GuardrailDef;
import org.conductoross.conductor.ai.model.PromptTemplate;
import org.conductoross.conductor.ai.model.ToolDef;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Discovers {@link AgentDef}-annotated methods
 * via reflection and resolves them into {@link Agent} instances.
 *
 * <p>Parallel to {@link ToolRegistry}. Prefer the public entry points
 * {@link Agent#fromInstance(Object)} and {@link Agent#fromInstance(Object, String)}.
 */
public final class AgentRegistry {
    private static final Logger logger = LoggerFactory.getLogger(AgentRegistry.class);

    private AgentRegistry() {}

    /**
     * Resolve all {@code @AgentDef}-annotated methods on an object into Agent instances.
     *
     * @param obj the object to inspect
     * @return list of resolved agents
     */
    public static List<Agent> fromInstance(Object obj) {
        Map<String, Method> methods = agentMethods(obj);
        List<Agent> agents = new ArrayList<>();
        for (Map.Entry<String, Method> entry : methods.entrySet()) {
            agents.add(resolve(obj, methods, entry.getKey(), "", new ArrayDeque<>()));
        }
        return agents;
    }

    /**
     * Resolve a single {@code @AgentDef}-annotated method by its resolved agent name.
     *
     * @param obj  the object to inspect
     * @param name the agent name (annotation {@code name} or the method name)
     * @return the resolved agent
     * @throws IllegalArgumentException if no agent with that name is defined on the object
     */
    public static Agent fromInstance(Object obj, String name) {
        Map<String, Method> methods = agentMethods(obj);
        if (!methods.containsKey(name)) {
            throw new IllegalArgumentException("No @AgentDef method named '" + name + "' on "
                    + obj.getClass().getName() + ". Available: " + methods.keySet());
        }
        return resolve(obj, methods, name, "", new ArrayDeque<>());
    }

    /**
     * Discover all {@code @AgentDef}-annotated methods, keyed by resolved agent name.
     *
     * <p>Walks the full type hierarchy (superclasses, then interfaces) rather than
     * {@code getMethods()}, for two reasons:
     * <ul>
     *   <li>An unannotated override must not hide an annotated ancestor declaration —
     *       a CGLIB-style proxy (e.g. a {@code @Transactional} Spring bean) overrides
     *       every public method without copying annotations. The ancestor's annotated
     *       {@link Method} is used; invocation still dispatches virtually, so the
     *       override (proxy behavior) executes. Nearest annotated declaration wins.</li>
     *   <li>A non-public annotated method is a user error and must fail loudly, not
     *       be silently invisible.</li>
     * </ul>
     */
    private static Map<String, Method> agentMethods(Object obj) {
        Map<String, Method> methods = new LinkedHashMap<>();
        Set<String> claimedSignatures = new HashSet<>();
        Deque<Class<?>> queue = new ArrayDeque<>();
        Set<Class<?>> visited = new HashSet<>();
        for (Class<?> c = obj.getClass(); c != null && c != Object.class; c = c.getSuperclass()) {
            queue.add(c);
        }
        while (!queue.isEmpty()) {
            Class<?> type = queue.poll();
            if (!visited.add(type)) continue;
            queue.addAll(Arrays.asList(type.getInterfaces()));
            for (Method method : type.getDeclaredMethods()) {
                if (method.isSynthetic()) continue;
                AgentDef ann = method.getAnnotation(AgentDef.class);
                if (ann == null) continue;
                String signature = method.getName() + Arrays.toString(method.getParameterTypes());
                if (!claimedSignatures.add(signature)) continue; // nearer declaration already claimed it
                if (!Modifier.isPublic(method.getModifiers())) {
                    throw new IllegalArgumentException(
                            "@AgentDef method " + method.getName() + " on " + type.getName() + " must be public");
                }
                if (method.isAnnotationPresent(Tool.class)
                        || method.isAnnotationPresent(org.conductoross.conductor.ai.annotations.GuardrailDef.class)) {
                    throw new IllegalArgumentException("Method " + method.getName() + " on " + type.getName()
                            + " cannot combine @AgentDef with @Tool or @GuardrailDef");
                }
                String name = ann.name().isEmpty() ? method.getName() : ann.name();
                Method previous = methods.put(name, method);
                if (previous != null) {
                    throw new IllegalArgumentException("Duplicate @AgentDef name '" + name + "' on "
                            + obj.getClass().getName() + " (methods " + previous.getName() + " and "
                            + method.getName() + ")");
                }
            }
        }
        return methods;
    }

    private static Agent resolve(
            Object obj, Map<String, Method> methods, String name, String parentModel, Deque<String> stack) {
        if (stack.contains(name)) {
            List<String> cycle = new ArrayList<>(stack);
            cycle.add(name);
            throw new IllegalArgumentException("Cyclic @AgentDef sub-agent reference: " + String.join(" -> ", cycle));
        }
        stack.push(name);
        try {
            Method method = methods.get(name);
            AgentDef ann = method.getAnnotation(AgentDef.class);
            validateSignature(obj, method);

            // Pure factory: a no-arg method returning Agent or Agent.Builder builds the
            // whole definition itself (CrewAI-style). The annotation is a discovery
            // marker only — non-default attributes would be silently ignored, so reject.
            Class<?> returnType = method.getReturnType();
            boolean pureFactory =
                    method.getParameterCount() == 0 && (returnType == Agent.class || returnType == Agent.Builder.class);
            if (pureFactory) {
                requireDiscoveryOnlyAttributes(obj, method, ann);
                return buildFromFactoryResult(obj, method, invoke(obj, method));
            }

            String model = !ann.model().isEmpty() ? ann.model() : parentModel;

            Agent.Builder builder = Agent.builder()
                    .name(name)
                    .instructions(ann.instructions())
                    .maxTurns(ann.maxTurns())
                    .strategy(ann.strategy());
            if (!model.isEmpty()) builder.model(model);
            if (ann.maxTokens() > 0) builder.maxTokens(ann.maxTokens());
            if (!Double.isNaN(ann.temperature())) builder.temperature(ann.temperature());
            if (ann.credentials().length > 0) builder.credentials(Arrays.asList(ann.credentials()));
            if (ann.contextWindowBudget() > 0) builder.contextWindowBudget(ann.contextWindowBudget());

            List<ToolDef> tools =
                    selectByName(ToolRegistry.fromInstance(obj), ToolDef::getName, ann.tools(), "@Tool", obj);
            if (!tools.isEmpty()) builder.tools(tools);

            List<GuardrailDef> guardrails = selectByName(
                    ToolRegistry.guardrailsFromInstance(obj),
                    GuardrailDef::getName,
                    ann.guardrails(),
                    "@GuardrailDef",
                    obj);
            if (!guardrails.isEmpty()) builder.guardrails(guardrails);

            if (ann.agents().length > 0) {
                List<Agent> subAgents = new ArrayList<>();
                for (String subName : ann.agents()) {
                    if (!methods.containsKey(subName)) {
                        throw new IllegalArgumentException("Sub-agent '" + subName + "' referenced by @AgentDef '"
                                + name + "' not found on " + obj.getClass().getName()
                                + ". Available: " + methods.keySet());
                    }
                    subAgents.add(resolve(obj, methods, subName, model, stack));
                }
                builder.agents(subAgents);
            }

            Agent agent = invokeAgentMethod(obj, method, ann, builder);
            logger.debug("Resolved agent '{}' from {}", name, obj.getClass().getSimpleName());
            return agent;
        } finally {
            stack.pop();
        }
    }

    /**
     * Enforce the {@code @AgentDef} method contract. The return type declares what
     * the method provides:
     * <ul>
     *   <li>{@code void} — nothing; the annotation alone defines the agent</li>
     *   <li>{@code String} — dynamic instructions</li>
     *   <li>{@code PromptTemplate} — a server-side instructions template</li>
     *   <li>{@code Agent.Builder} — the definition itself; the returned builder is built</li>
     *   <li>{@code Agent} — the definition itself, returned as-is (full factory)</li>
     * </ul>
     * Parameters: none, or a single {@link Agent.Builder} (pre-populated from the
     * annotation and discovered tools/guardrails/sub-agents).
     */
    private static void validateSignature(Object obj, Method method) {
        Class<?> returnType = method.getReturnType();
        if (returnType != String.class
                && returnType != void.class
                && returnType != Void.class
                && returnType != PromptTemplate.class
                && returnType != Agent.class
                && returnType != Agent.Builder.class) {
            throw new IllegalArgumentException("@AgentDef method " + method.getName() + " on "
                    + obj.getClass().getName()
                    + " must return String, PromptTemplate, Agent, Agent.Builder, or void; got "
                    + returnType.getSimpleName());
        }
        Class<?>[] params = method.getParameterTypes();
        if (params.length > 1 || (params.length == 1 && params[0] != Agent.Builder.class)) {
            throw new IllegalArgumentException("@AgentDef method " + method.getName() + " on "
                    + obj.getClass().getName()
                    + " must take no parameters, or a single Agent.Builder to customize");
        }
    }

    /**
     * Invoke the agent method after the builder is pre-populated from the
     * annotation, then build the agent. Dispatch is by declared return type:
     *
     * <ul>
     *   <li>{@code void}, no-arg — pure marker; never invoked.</li>
     *   <li>{@code void} + builder param — customizer; invoked once.</li>
     *   <li>{@code String}, no-arg — <em>lazy</em> dynamic instructions: the method is
     *       re-invoked every time {@link Agent#getInstructions()} resolves (each run
     *       submission), matching the Python SDK where callable instructions resolve
     *       at serialization time. A non-empty result wins over the annotation
     *       attribute.</li>
     *   <li>{@code String} + builder param — invoked once, eagerly: re-running a
     *       customizer per serialization would replay its side effects.</li>
     *   <li>{@code PromptTemplate} — invoked once; a non-null result becomes
     *       {@code instructionsTemplate}.</li>
     *   <li>{@code Agent.Builder} / {@code Agent} + builder param — the returned
     *       value is the definition (built if a builder).</li>
     * </ul>
     */
    private static Agent invokeAgentMethod(Object obj, Method method, AgentDef ann, Agent.Builder builder) {
        Class<?> returnType = method.getReturnType();
        boolean wantsBuilder = method.getParameterCount() == 1;

        if (returnType == String.class && !wantsBuilder) {
            builder.instructions(() -> {
                Object dynamic = invoke(obj, method);
                return (dynamic instanceof String s && !s.isEmpty()) ? s : ann.instructions();
            });
            return builder.build();
        }

        Object result = (returnType == void.class || returnType == Void.class) && !wantsBuilder
                ? null // pure marker — nothing to invoke
                : (wantsBuilder ? invoke(obj, method, builder) : invoke(obj, method));

        if (returnType == String.class) {
            if (result instanceof String dynamic && !dynamic.isEmpty()) {
                builder.instructions(dynamic);
            }
        } else if (returnType == PromptTemplate.class) {
            if (result != null) {
                builder.instructionsTemplate((PromptTemplate) result);
            }
        } else if (returnType == Agent.class || returnType == Agent.Builder.class) {
            return buildFromFactoryResult(obj, method, result);
        }
        return builder.build();
    }

    /** Turn an {@code Agent}/{@code Agent.Builder} factory result into the agent. */
    private static Agent buildFromFactoryResult(Object obj, Method method, Object result) {
        if (result == null) {
            throw new IllegalArgumentException("@AgentDef factory method " + method.getName() + " on "
                    + obj.getClass().getName() + " returned null; it must return the agent definition");
        }
        return result instanceof Agent.Builder b ? b.build() : (Agent) result;
    }

    /**
     * Reject non-default annotation attributes on a pure factory method (no-arg,
     * returning {@code Agent} or {@code Agent.Builder}) — the factory builds the
     * whole definition, so attributes other than {@code name} would be silently
     * ignored. Methods that accept the pre-populated builder may use attributes.
     */
    private static void requireDiscoveryOnlyAttributes(Object obj, Method method, AgentDef ann) {
        List<String> set = new ArrayList<>();
        if (!ann.model().isEmpty()) set.add("model");
        if (!ann.instructions().isEmpty()) set.add("instructions");
        if (!Arrays.equals(ann.tools(), new String[] {"*"})) set.add("tools");
        if (!Arrays.equals(ann.guardrails(), new String[] {"*"})) set.add("guardrails");
        if (ann.agents().length > 0) set.add("agents");
        if (ann.strategy() != Strategy.HANDOFF) set.add("strategy");
        if (ann.maxTurns() != 25) set.add("maxTurns");
        if (ann.maxTokens() != 0) set.add("maxTokens");
        if (!Double.isNaN(ann.temperature())) set.add("temperature");
        if (ann.credentials().length > 0) set.add("credentials");
        if (ann.contextWindowBudget() != 0) set.add("contextWindowBudget");
        if (!set.isEmpty()) {
            throw new IllegalArgumentException("@AgentDef factory method " + method.getName() + " on "
                    + obj.getClass().getName() + " returns "
                    + method.getReturnType().getSimpleName()
                    + " and builds the definition itself, but sets annotation attributes " + set
                    + " that would be ignored. Either drop the attributes, or accept the"
                    + " pre-populated Agent.Builder as a parameter.");
        }
    }

    /** Reflectively invoke the agent method, unwrapping reflection exceptions. */
    private static Object invoke(Object obj, Method method, Object... args) {
        try {
            method.setAccessible(true);
            return method.invoke(obj, args);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("Failed to invoke @AgentDef method " + method.getName(), e);
        }
    }

    /**
     * Filter discovered definitions by the annotation's name list:
     * {@code {"*"}} selects all, an empty array selects none, otherwise match by
     * name and throw on unknown names.
     */
    private static <T> List<T> selectByName(
            List<T> all, java.util.function.Function<T, String> nameOf, String[] requested, String kind, Object obj) {
        if (requested.length == 1 && "*".equals(requested[0])) {
            return all;
        }
        List<T> selected = new ArrayList<>();
        for (String want : requested) {
            T match = all.stream()
                    .filter(t -> want.equals(nameOf.apply(t)))
                    .findFirst()
                    .orElseThrow(() -> new IllegalArgumentException("No " + kind + " method named '" + want
                            + "' on " + obj.getClass().getName() + ". Available: "
                            + all.stream().map(nameOf).toList()));
            selected.add(match);
        }
        return selected;
    }
}
