// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.frameworks;

import ai.agentspan.Agent;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.ToolDef;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Bridges LangChain4j tool objects to Agentspan {@link Agent}.
 *
 * <p>Users who have existing POJOs annotated with
 * {@code @dev.langchain4j.agent.tool.Tool} can hand them directly to
 * {@link #from} and get back a fully-configured {@link Agent} whose tools
 * are backed by those Java methods.
 *
 * <p>LangChain4j is an <em>optional</em> dependency of the SDK.  This class
 * is compiled in when the library is on the classpath; at runtime it will
 * throw {@link ClassNotFoundException} (wrapped in an unchecked exception) if
 * LangChain4j is absent.
 *
 * <p>Example:
 * <pre>{@code
 * Agent agent = LangChain4jAgent.from(
 *     "my_agent",
 *     "openai/gpt-4o-mini",
 *     "You are a helpful calculator.",
 *     new CalculatorTools()
 * );
 * AgentResult result = runtime.run(agent, "What is 7 + 8?");
 * }</pre>
 */
public class LangChain4jAgent {

    private LangChain4jAgent() {}

    // ── Public API ───────────────────────────────────────────────────────────

    /**
     * Create an Agentspan {@link Agent} from one or more LangChain4j tool objects.
     *
     * @param name         agent name (must match {@code ^[a-zA-Z_][a-zA-Z0-9_-]*$})
     * @param model        LLM model string, e.g. {@code "openai/gpt-4o-mini"}
     * @param instructions system prompt / instructions for the agent
     * @param toolObjects  objects with {@code @dev.langchain4j.agent.tool.Tool} methods
     * @return an Agentspan Agent ready to pass to
     *         {@link ai.agentspan.AgentRuntime#plan(Agent)} or
     *         {@link ai.agentspan.AgentRuntime#run(Agent, String)}
     */
    public static Agent from(
            String name,
            String model,
            String instructions,
            Object... toolObjects) {

        List<ToolDef> tools = extractTools(toolObjects);

        return Agent.builder()
                .name(name)
                .model(model)
                .instructions(instructions)
                .tools(tools)
                .build();
    }

    /**
     * Return {@code true} if {@code obj} has at least one method annotated
     * with {@code @dev.langchain4j.agent.tool.Tool}.
     *
     * <p>Used to detect whether a POJO is a LangChain4j tool provider.
     *
     * @param obj any object
     * @return {@code true} if the object carries LangChain4j {@code @Tool} methods
     */
    public static boolean isLangChain4jTools(Object obj) {
        if (obj == null) return false;
        for (Method m : obj.getClass().getMethods()) {
            if (isLangChain4jToolMethod(m)) {
                return true;
            }
        }
        return false;
    }

    // ── Package-private helpers (visible to tests) ───────────────────────────

    /**
     * Extract Agentspan {@link ToolDef} objects from an array of LangChain4j
     * {@code @Tool}-annotated objects.
     *
     * @param toolObjects objects to inspect via reflection
     * @return list of {@link ToolDef} instances
     */
    static List<ToolDef> extractTools(Object[] toolObjects) {
        List<ToolDef> tools = new ArrayList<>();
        if (toolObjects == null) return tools;

        for (Object obj : toolObjects) {
            if (obj == null) continue;
            for (Method method : obj.getClass().getMethods()) {
                if (!isLangChain4jToolMethod(method)) continue;

                // Resolve name and description from @Tool annotation
                String toolName = resolveToolName(method);
                String description = resolveDescription(method);

                // Build input JSON Schema (honours @P parameter names)
                Map<String, Object> inputSchema = buildInputSchema(method);

                // Build output JSON Schema from return type
                Map<String, Object> outputSchema = ToolRegistry.typeToJsonSchema(method.getReturnType());

                // Wrap method invocation via reflection (same pattern as ToolRegistry)
                method.setAccessible(true);
                final Object instance = obj;
                final Method finalMethod = method;
                final String finalName = toolName;
                Function<Map<String, Object>, Object> func = inputData -> {
                    try {
                        Object[] args = buildMethodArgs(finalMethod, inputData);
                        return finalMethod.invoke(instance, args);
                    } catch (Exception e) {
                        throw new RuntimeException("LangChain4j tool execution failed: " + finalName, e);
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

    // ── Private helpers ───────────────────────────────────────────────────────

    /**
     * Return {@code true} if {@code m} is annotated with
     * {@code @dev.langchain4j.agent.tool.Tool}.
     *
     * <p>Uses reflection instead of a direct annotation import so this class
     * compiles even when LangChain4j is absent from the classpath at
     * <em>compile</em> time (the dependency is {@code optional}).  At runtime,
     * if LangChain4j is present the check works; if absent, the method simply
     * returns {@code false} for every method.
     */
    private static boolean isLangChain4jToolMethod(Method m) {
        for (java.lang.annotation.Annotation ann : m.getAnnotations()) {
            if (ann.annotationType().getName().equals("dev.langchain4j.agent.tool.Tool")) {
                return true;
            }
        }
        return false;
    }

    /**
     * Resolve the tool name from the {@code @Tool} annotation.
     * Falls back to the Java method name when the annotation's {@code name()}
     * is empty.
     */
    private static String resolveToolName(Method method) {
        for (java.lang.annotation.Annotation ann : method.getAnnotations()) {
            if (!ann.annotationType().getName().equals("dev.langchain4j.agent.tool.Tool")) continue;
            try {
                String name = (String) ann.annotationType().getMethod("name").invoke(ann);
                if (name != null && !name.isEmpty()) return name;
            } catch (Exception ignored) {}
        }
        return method.getName();
    }

    /**
     * Resolve the tool description from {@code @Tool.value()}.
     * The {@code value()} is a {@code String[]} — joined with space.
     */
    private static String resolveDescription(Method method) {
        for (java.lang.annotation.Annotation ann : method.getAnnotations()) {
            if (!ann.annotationType().getName().equals("dev.langchain4j.agent.tool.Tool")) continue;
            try {
                Object value = ann.annotationType().getMethod("value").invoke(ann);
                if (value instanceof String[]) {
                    String[] parts = (String[]) value;
                    if (parts.length > 0) {
                        return String.join(" ", parts);
                    }
                }
            } catch (Exception ignored) {}
        }
        return "";
    }

    /**
     * Build a JSON Schema {@code {type: object, properties: {...}, required: [...]}}
     * for the given method's parameters.
     *
     * <p>Parameter names are resolved in order:
     * <ol>
     *   <li>{@code @dev.langchain4j.agent.tool.P} annotation's {@code value()}</li>
     *   <li>Compiler-retained parameter name (requires {@code -parameters} flag)</li>
     *   <li>Positional fallback {@code arg0}, {@code arg1}, …</li>
     * </ol>
     */
    private static Map<String, Object> buildInputSchema(Method method) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        Map<String, Object> props = new LinkedHashMap<>();
        List<String> required = new ArrayList<>();

        Parameter[] params = method.getParameters();
        for (int i = 0; i < params.length; i++) {
            Parameter param = params[i];
            String paramName = resolveParamName(param, i);
            Map<String, Object> propSchema = ToolRegistry.typeToJsonSchema(param.getParameterizedType());

            // Incorporate @P description if present
            String pDesc = resolvePDescription(param);
            if (pDesc != null && !pDesc.isEmpty()) {
                // Clone and add description
                Map<String, Object> withDesc = new LinkedHashMap<>(propSchema);
                withDesc.put("description", pDesc);
                propSchema = withDesc;
            }

            props.put(paramName, propSchema);
            required.add(paramName);
        }

        schema.put("properties", props);
        if (!required.isEmpty()) {
            schema.put("required", required);
        }
        return schema;
    }

    /**
     * Resolve a parameter name from (in priority order):
     * 1. {@code @P} annotation value
     * 2. Compiler-retained name (not "arg0")
     * 3. Positional fallback "arg{i}"
     */
    private static String resolveParamName(Parameter param, int index) {
        // Check @P first
        for (java.lang.annotation.Annotation ann : param.getAnnotations()) {
            if (ann.annotationType().getName().equals("dev.langchain4j.agent.tool.P")) {
                try {
                    String name = (String) ann.annotationType().getMethod("value").invoke(ann);
                    if (name != null && !name.isEmpty()) return name;
                } catch (Exception ignored) {}
            }
        }
        // Compiler-retained name
        String name = param.getName();
        if (name != null && !name.startsWith("arg")) {
            return name;
        }
        return "arg" + index;
    }

    /**
     * Return the description from {@code @P(value="name")} when the annotation
     * does not hold a param description, or {@code null} if not annotated.
     *
     * <p>Note: in LangChain4j, {@code @P.value()} is the parameter <em>name</em>
     * used in the schema, not a separate description field.  We do not emit
     * an extra description at the property level unless {@code @P} carries one.
     */
    private static String resolvePDescription(Parameter param) {
        // @P in langchain4j 1.x has only value() (name) and required();
        // there is no separate description field, so return null.
        return null;
    }

    /**
     * Build the Java method argument array from the tool input map.
     *
     * <p>Mirrors the logic in {@link ToolRegistry#buildMethodArgs} but reads
     * {@code @P} annotations for parameter names instead of compiler-retained names.
     */
    private static Object[] buildMethodArgs(Method method, Map<String, Object> inputData) {
        Parameter[] params = method.getParameters();
        Object[] args = new Object[params.length];

        for (int i = 0; i < params.length; i++) {
            Parameter param = params[i];
            String paramName = resolveParamName(param, i);
            Object raw = inputData != null ? inputData.get(paramName) : null;
            args[i] = coerce(raw, param.getType());
        }
        return args;
    }

    /**
     * Coerce a raw value (from JSON deserialization) to the target Java type.
     * Delegates to {@link ToolRegistry}'s logic for numeric conversions.
     */
    private static Object coerce(Object value, Class<?> targetType) {
        if (value == null) return defaultFor(targetType);
        if (targetType.isInstance(value)) return value;

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
