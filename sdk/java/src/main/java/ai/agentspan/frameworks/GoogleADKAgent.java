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
 * Bridges the Google ADK (Agent Development Kit) shape to Agentspan {@link Agent}.
 *
 * <p>Mirrors the Python pattern:
 * <pre>{@code
 * from google.adk.agents import Agent
 * agent = Agent(name="greeter", instruction="...", model="gemini-2.0-flash")
 * runtime.run(agent, "Say hi")
 * }</pre>
 *
 * <p>In Java the equivalent is:
 * <pre>{@code
 * Agent agent = GoogleADKAgent.builder()
 *     .name("greeter")
 *     .instruction("You are a friendly greeter")  // note: singular
 *     .model("gemini-2.0-flash")
 *     .build();
 * Agentspan.run(agent, "Say hi");
 * }</pre>
 *
 * <p>ADK differs from OpenAI in three ways at the wire level:
 * <ul>
 *   <li>{@code instruction} (singular) — not {@code instructions}</li>
 *   <li>{@code sub_agents} — not {@code handoffs}</li>
 *   <li>Bare model names like {@code "gemini-2.0-flash"} get prefixed with
 *       {@code "google_gemini/"} server-side.</li>
 * </ul>
 *
 * <p>The server's {@code GoogleADKNormalizer} consumes the wire payload. Tools
 * are extracted via the same reflection bridge as {@link OpenAIAgent}.
 */
public final class GoogleADKAgent {

    private GoogleADKAgent() {}

    public static Builder builder() {
        return new Builder();
    }

    /**
     * Build an ADK Agent from a name + instruction + model + tool objects.
     * Convenience shortcut for the common case.
     */
    public static Agent from(String name, String model, String instruction, Object... toolObjects) {
        return builder()
                .name(name)
                .model(model)
                .instruction(instruction)
                .tools(toolObjects)
                .build();
    }

    public static final class Builder {
        private String name;
        private String model;
        private String instruction;
        private final List<ToolDef> tools = new ArrayList<>();
        private final List<Agent> subAgents = new ArrayList<>();
        private String outputType;

        public Builder name(String name) { this.name = name; return this; }
        public Builder model(String model) { this.model = model; return this; }

        /** Singular form per ADK convention. */
        public Builder instruction(String instruction) { this.instruction = instruction; return this; }

        public Builder tools(Object... toolObjects) {
            this.tools.addAll(extractTools(toolObjects));
            return this;
        }

        public Builder toolDefs(Collection<ToolDef> defs) {
            this.tools.addAll(defs);
            return this;
        }

        /** ADK "sub_agents": child agents this agent can delegate to. */
        public Builder subAgents(Agent... agents) {
            for (Agent a : agents) this.subAgents.add(a);
            return this;
        }

        public Builder outputType(String typeName) { this.outputType = typeName; return this; }

        public Agent build() {
            if (name == null || name.isEmpty()) {
                throw new IllegalArgumentException("GoogleADKAgent.name is required");
            }
            Agent.Builder b = Agent.builder()
                    .name(name)
                    .framework("google_adk");
            if (model != null && !model.isEmpty()) b.model(model);
            // Server expects "instruction" not "instructions" — serializer
            // handles that swap when framework="google_adk".
            if (instruction != null && !instruction.isEmpty()) b.instructions(instruction);
            if (!tools.isEmpty()) b.tools(tools.toArray(new ToolDef[0]));

            Map<String, Object> frameworkConfig = new LinkedHashMap<>();
            if (!subAgents.isEmpty()) {
                List<Map<String, Object>> subs = new ArrayList<>();
                for (Agent s : subAgents) {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("name", s.getName());
                    if (s.getInstructions() != null) m.put("instruction", s.getInstructions());
                    if (s.getModel() != null) m.put("model", s.getModel());
                    subs.add(m);
                }
                frameworkConfig.put("sub_agents", subs);
            }
            if (outputType != null && !outputType.isEmpty()) {
                frameworkConfig.put("output_type", outputType);
            }
            if (!frameworkConfig.isEmpty()) b.frameworkConfig(frameworkConfig);

            return b.build();
        }
    }

    // ── Tool reflection (mirrors OpenAIAgent) ──────────────────────────────

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
                    } catch (Exception e) {
                        throw new RuntimeException("Google ADK tool execution failed: " + finalName, e);
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
        return "arg" + idx;
    }

    private static Object[] buildMethodArgs(Method method, Map<String, Object> inputData) {
        Parameter[] params = method.getParameters();
        Object[] args = new Object[params.length];
        for (int i = 0; i < params.length; i++) {
            String pn = resolveParamName(params[i], i);
            Object raw = inputData != null ? inputData.get(pn) : null;
            args[i] = coerce(raw, params[i].getType());
        }
        return args;
    }

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
