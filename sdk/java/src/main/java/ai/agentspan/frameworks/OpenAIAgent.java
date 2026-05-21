// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.frameworks;

import ai.agentspan.Agent;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.ToolDef;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Bridges the OpenAI Agents SDK shape to Agentspan {@link Agent}.
 *
 * <p>Mirrors the Python pattern:
 * <pre>{@code
 * from agents import Agent
 * agent = Agent(name="greeter", instructions="...", model="openai/gpt-4o-mini")
 * runtime.run(agent, "Say hi")
 * }</pre>
 *
 * <p>In Java the equivalent is:
 * <pre>{@code
 * Agent agent = OpenAIAgent.builder()
 *     .name("greeter")
 *     .instructions("You are a helpful assistant")
 *     .model("openai/gpt-4o")
 *     .build();
 * Agentspan.run(agent, "Say hi");
 * }</pre>
 *
 * <p>The server's {@code OpenAINormalizer} consumes the wire payload (the SDK
 * routes through {@code framework="openai"} + {@code rawConfig}). Model names
 * without a provider prefix are auto-prefixed with {@code openai/} server-side.
 *
 * <p>Local @Tool-annotated POJOs are wrapped using the same reflection bridge
 * as {@link LangChain4jAgent} — they are registered as Agentspan worker tools
 * and the OpenAI Agents server-side runner calls them via the standard tool-call
 * dispatch.
 */
public final class OpenAIAgent {

    private OpenAIAgent() {}

    public static Builder builder() {
        return new Builder();
    }

    /**
     * Build an OpenAI Agent from a name + instructions + model + tool objects.
     * Convenience shortcut for the common case.
     */
    public static Agent from(String name, String model, String instructions, Object... toolObjects) {
        return builder()
                .name(name)
                .model(model)
                .instructions(instructions)
                .tools(toolObjects)
                .build();
    }

    public static final class Builder {
        private String name;
        private String model;
        private String instructions;
        private final List<ToolDef> tools = new ArrayList<>();
        private final List<Agent> handoffs = new ArrayList<>();
        private String outputType;

        public Builder name(String name) { this.name = name; return this; }
        public Builder model(String model) { this.model = model; return this; }
        public Builder instructions(String instructions) { this.instructions = instructions; return this; }

        /** Add @Tool-annotated POJO(s); each annotated method becomes an Agentspan worker tool. */
        public Builder tools(Object... toolObjects) {
            this.tools.addAll(extractTools(toolObjects));
            return this;
        }

        /** Add already-built {@link ToolDef}s. */
        public Builder toolDefs(Collection<ToolDef> defs) {
            this.tools.addAll(defs);
            return this;
        }

        /** OpenAI Agents SDK "handoffs": sub-agents the LLM can transfer control to. */
        public Builder handoffs(Agent... agents) {
            for (Agent a : agents) this.handoffs.add(a);
            return this;
        }

        /** Optional structured-output type name (the server hooks into its structured-output normalizer). */
        public Builder outputType(String typeName) { this.outputType = typeName; return this; }

        public Agent build() {
            if (name == null || name.isEmpty()) {
                throw new IllegalArgumentException("OpenAIAgent.name is required");
            }
            Agent.Builder b = Agent.builder()
                    .name(name)
                    .framework("openai");
            if (model != null && !model.isEmpty()) b.model(model);
            if (instructions != null && !instructions.isEmpty()) b.instructions(instructions);
            if (!tools.isEmpty()) b.tools(tools.toArray(new ToolDef[0]));

            Map<String, Object> frameworkConfig = new LinkedHashMap<>();
            if (!handoffs.isEmpty()) {
                List<Map<String, Object>> hs = new ArrayList<>();
                for (Agent h : handoffs) {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("name", h.getName());
                    if (h.getInstructions() != null) m.put("instructions", h.getInstructions());
                    if (h.getModel() != null) m.put("model", h.getModel());
                    hs.add(m);
                }
                frameworkConfig.put("handoffs", hs);
            }
            if (outputType != null && !outputType.isEmpty()) {
                frameworkConfig.put("output_type", outputType);
            }
            if (!frameworkConfig.isEmpty()) b.frameworkConfig(frameworkConfig);

            return b.build();
        }
    }

    // ── Tool reflection (shared shape with LangChain4jAgent) ────────────────

    /**
     * Recognise tool POJOs whose methods carry the OpenAI Agents SDK
     * {@code @function_tool} decorator (Python) — in Java we accept
     * {@code @dev.langchain4j.agent.tool.Tool}-annotated POJOs as a
     * pragmatic equivalent, since neither the OpenAI Java client nor
     * the OpenAI Agents SDK define a Java tool annotation.
     */
    private static List<ToolDef> extractTools(Object[] toolObjects) {
        List<ToolDef> tools = new ArrayList<>();
        if (toolObjects == null) return tools;
        for (Object obj : toolObjects) {
            if (obj == null) continue;
            for (Method method : obj.getClass().getMethods()) {
                if (!isToolMethod(method)) continue;
                String toolName = resolveToolName(method);
                String description = resolveDescription(method);
                Map<String, Object> inputSchema = buildInputSchema(method);
                Map<String, Object> outputSchema = ToolRegistry.typeToJsonSchema(method.getReturnType());

                method.setAccessible(true);
                final Object instance = obj;
                final Method finalMethod = method;
                final String finalName = toolName;
                Function<Map<String, Object>, Object> func = inputData -> {
                    try {
                        Object[] args = buildMethodArgs(finalMethod, inputData);
                        return finalMethod.invoke(instance, args);
                    } catch (java.lang.reflect.InvocationTargetException ite) {
                        // Unwrap so the user sees their own exception, not a
                        // confusing double-wrap.
                        Throwable cause = ite.getCause() != null ? ite.getCause() : ite;
                        if (cause instanceof RuntimeException re) throw re;
                        throw new RuntimeException("OpenAI tool '" + finalName + "' threw: "
                                + cause.getMessage(), cause);
                    } catch (IllegalAccessException | IllegalArgumentException ex) {
                        throw new RuntimeException("OpenAI tool '" + finalName
                                + "' invocation failed (check parameter types and the "
                                + "-parameters compiler flag): " + ex.getMessage(), ex);
                    }
                };

                tools.add(new ToolDef.Builder()
                        .name(toolName)
                        .description(description)
                        .inputSchema(inputSchema)
                        .outputSchema(outputSchema)
                        .func(func)
                        .toolType("worker")
                        .build());
            }
        }
        return tools;
    }

    private static boolean isToolMethod(Method m) {
        for (java.lang.annotation.Annotation ann : m.getAnnotations()) {
            String name = ann.annotationType().getName();
            if (name.equals("dev.langchain4j.agent.tool.Tool")) return true;
            if (name.equals("ai.agentspan.annotations.Tool")) return true;
        }
        return false;
    }

    private static String resolveToolName(Method method) {
        for (java.lang.annotation.Annotation ann : method.getAnnotations()) {
            String anName = ann.annotationType().getName();
            if (anName.equals("dev.langchain4j.agent.tool.Tool")
                    || anName.equals("ai.agentspan.annotations.Tool")) {
                try {
                    String name = (String) ann.annotationType().getMethod("name").invoke(ann);
                    if (name != null && !name.isEmpty()) return name;
                } catch (Exception ignored) {}
            }
        }
        return method.getName();
    }

    private static String resolveDescription(Method method) {
        for (java.lang.annotation.Annotation ann : method.getAnnotations()) {
            String anName = ann.annotationType().getName();
            if (anName.equals("dev.langchain4j.agent.tool.Tool")) {
                try {
                    Object value = ann.annotationType().getMethod("value").invoke(ann);
                    if (value instanceof String[]) {
                        String[] parts = (String[]) value;
                        if (parts.length > 0) return String.join(" ", parts);
                    }
                } catch (Exception ignored) {}
            }
            if (anName.equals("ai.agentspan.annotations.Tool")) {
                try {
                    Object value = ann.annotationType().getMethod("value").invoke(ann);
                    if (value instanceof String) return (String) value;
                } catch (Exception ignored) {}
            }
        }
        return "";
    }

    private static Map<String, Object> buildInputSchema(Method method) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        Map<String, Object> props = new LinkedHashMap<>();
        List<String> required = new ArrayList<>();
        Parameter[] params = method.getParameters();
        for (int i = 0; i < params.length; i++) {
            Parameter p = params[i];
            String pn = resolveParamName(p, i);
            props.put(pn, ToolRegistry.typeToJsonSchema(p.getParameterizedType()));
            required.add(pn);
        }
        schema.put("properties", props);
        if (!required.isEmpty()) schema.put("required", required);
        return schema;
    }

    private static final java.util.Set<String> WARNED_ARG_METHODS =
            java.util.concurrent.ConcurrentHashMap.newKeySet();

    private static String resolveParamName(Parameter p, int idx) {
        for (java.lang.annotation.Annotation ann : p.getAnnotations()) {
            if (ann.annotationType().getName().equals("dev.langchain4j.agent.tool.P")) {
                try {
                    String v = (String) ann.annotationType().getMethod("value").invoke(ann);
                    if (v != null && !v.isEmpty()) return v;
                } catch (Exception ignored) {}
            }
        }
        String name = p.getName();
        if (name != null && !name.startsWith("arg")) return name;
        // Compiler-retained names require javac -parameters. Without it the
        // LLM sees meaningless arg0/arg1 — warn once-per-method so the user
        // notices instead of silently shipping a garbage schema.
        String key = p.getDeclaringExecutable().getDeclaringClass().getName()
                + "#" + p.getDeclaringExecutable().getName();
        if (WARNED_ARG_METHODS.add(key)) {
            org.slf4j.LoggerFactory.getLogger(OpenAIAgent.class).warn(
                    "OpenAIAgent: method '{}' parameter names are not preserved. "
                    + "The LLM will see meaningless 'arg{}' parameter names. Compile "
                    + "with javac -parameters or use @P(\"...\") on each parameter.",
                    key, idx);
        }
        return "arg" + idx;
    }

    private static Object[] buildMethodArgs(Method method, Map<String, Object> inputData) {
        Parameter[] params = method.getParameters();
        Object[] args = new Object[params.length];
        for (int i = 0; i < params.length; i++) {
            String pn = resolveParamName(params[i], i);
            Object raw = inputData != null ? inputData.get(pn) : null;
            // Share ToolRegistry's coercion table: primitives + String +
            // Boolean + java.time.* + enums + Optional + List<X>/Map/arrays
            // via Jackson. Without this, declaring a LocalDate / List<Double>
            // / enum param on an @Tool method would throw IllegalArgument at
            // invoke time.
            args[i] = ai.agentspan.internal.ToolRegistry.coerceArgument(
                    raw, params[i].getType(), params[i].getParameterizedType());
        }
        return args;
    }

    // The local coerce() / defaultFor() helpers below are retained as
    // dead-code fallbacks in case ToolRegistry.coerceArgument throws; the
    // primary path is the shared coercion table above.
    @SuppressWarnings("unused")
    private static Object coerce(Object value, Class<?> targetType) {
        if (value == null) return defaultFor(targetType);
        if (targetType.isInstance(value)) return value;
        if (targetType == String.class && (value instanceof Map || value instanceof List)) {
            try { return ai.agentspan.internal.JsonMapper.get().writeValueAsString(value); }
            catch (Exception e) { return value.toString(); }
        }
        String str = value.toString();
        if (targetType == String.class) return str;
        if (targetType == int.class || targetType == Integer.class) {
            return value instanceof Number ? ((Number) value).intValue() : Integer.parseInt(str);
        }
        if (targetType == long.class || targetType == Long.class) {
            return value instanceof Number ? ((Number) value).longValue() : Long.parseLong(str);
        }
        if (targetType == double.class || targetType == Double.class) {
            return value instanceof Number ? ((Number) value).doubleValue() : Double.parseDouble(str);
        }
        if (targetType == float.class || targetType == Float.class) {
            return value instanceof Number ? ((Number) value).floatValue() : Float.parseFloat(str);
        }
        if (targetType == boolean.class || targetType == Boolean.class) {
            if (value instanceof Boolean) return value;
            return Boolean.parseBoolean(str);
        }
        return value;
    }

    private static Object defaultFor(Class<?> type) {
        if (type == int.class) return 0;
        if (type == long.class) return 0L;
        if (type == double.class) return 0.0;
        if (type == float.class) return 0.0f;
        if (type == boolean.class) return false;
        return null;
    }
}
