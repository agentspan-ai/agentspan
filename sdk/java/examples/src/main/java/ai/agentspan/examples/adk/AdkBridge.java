// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.Agent;
import ai.agentspan.model.ToolDef;

import com.google.adk.agents.BaseAgent;
import com.google.adk.agents.Instruction;
import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.BaseTool;
import com.google.adk.tools.FunctionTool;
import com.google.genai.types.FunctionDeclaration;
import com.google.genai.types.Schema;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Adapter that takes a native Google ADK {@link LlmAgent} and returns an
 * Agentspan {@link Agent} ready for {@code Agentspan.run(...)}.
 *
 * <p>Inputs are real ADK objects built with {@code LlmAgent.builder()},
 * {@code FunctionTool.create(...)}, etc. — the example author writes
 * idiomatic ADK code; the bridge translates to the Agentspan wire format
 * so the agent runs on the durable Agentspan server.
 */
public final class AdkBridge {

    private AdkBridge() {}

    /**
     * Convert a native ADK {@link LlmAgent} into an Agentspan {@link Agent}.
     *
     * <p>Extracted: name, model string, instruction text, sub-agents,
     * and {@link FunctionTool} declarations + Java callbacks.
     */
    public static Agent toAgentspan(LlmAgent adk) {
        Agent.Builder b = Agent.builder()
                .name(adk.name())
                .framework("google_adk");

        adk.model().ifPresent(m -> m.modelName().ifPresent(b::model));

        String instructionText = extractInstruction(adk.instruction());
        if (instructionText != null && !instructionText.isEmpty()) {
            b.instructions(instructionText);
        }

        // ADK 1.3.0+ returns Single<List<BaseTool>>; resolve synchronously since
        // the bridge call site already serialises the agent on a worker thread.
        List<ToolDef> tools = extractTools(adk.tools().blockingGet());
        if (!tools.isEmpty()) {
            b.tools(tools.toArray(new ToolDef[0]));
        }

        Map<String, Object> frameworkConfig = new LinkedHashMap<>();
        List<? extends BaseAgent> subAgents = adk.subAgents();
        if (subAgents != null && !subAgents.isEmpty()) {
            List<Map<String, Object>> subs = new ArrayList<>();
            for (BaseAgent s : subAgents) {
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("name", s.name());
                if (s instanceof LlmAgent l) {
                    l.model().ifPresent(mdl -> mdl.modelName().ifPresent(name -> m.put("model", name)));
                    String inst = extractInstruction(l.instruction());
                    if (inst != null && !inst.isEmpty()) m.put("instruction", inst);
                }
                subs.add(m);
            }
            frameworkConfig.put("sub_agents", subs);
        }
        if (!frameworkConfig.isEmpty()) {
            b.frameworkConfig(frameworkConfig);
        }

        return b.build();
    }

    private static String extractInstruction(Instruction inst) {
        if (inst == null) return null;
        if (inst instanceof Instruction.Static s) {
            return s.instruction();
        }
        return null;
    }

    private static List<ToolDef> extractTools(List<BaseTool> baseTools) {
        List<ToolDef> out = new ArrayList<>();
        if (baseTools == null) return out;

        for (BaseTool t : baseTools) {
            if (!(t instanceof FunctionTool ft)) continue;

            Method method = ft.func();
            method.setAccessible(true);

            Map<String, Object> inputSchema = buildInputSchema(ft);
            Map<String, Object> outputSchema = new LinkedHashMap<>();
            outputSchema.put("type", "object");

            // ADK's FunctionTool.create(Class, "method") only resolves static
            // methods, so reflective invocation always passes a null receiver.
            final Method finalMethod = method;
            final String name = ft.name();
            Function<Map<String, Object>, Object> func = inputData -> {
                try {
                    Object[] args = buildArgs(finalMethod, inputData);
                    return finalMethod.invoke(null, args);
                } catch (Exception e) {
                    throw new RuntimeException("ADK FunctionTool execution failed: " + name, e);
                }
            };

            out.add(new ToolDef.Builder()
                    .name(ft.name())
                    .description(ft.description() == null ? "" : ft.description())
                    .inputSchema(inputSchema)
                    .outputSchema(outputSchema)
                    .func(func)
                    .toolType("worker")
                    .build());
        }
        return out;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> buildInputSchema(FunctionTool ft) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        Map<String, Object> properties = new LinkedHashMap<>();
        List<String> required = new ArrayList<>();

        // Try ADK's declaration first
        try {
            FunctionDeclaration decl = ft.declaration().orElse(null);
            if (decl != null) {
                Schema params = decl.parameters().orElse(null);
                if (params != null) {
                    params.properties().ifPresent(p -> {
                        for (Map.Entry<String, Schema> entry : p.entrySet()) {
                            properties.put(entry.getKey(), schemaToMap(entry.getValue()));
                        }
                    });
                    params.required().ifPresent(required::addAll);
                }
            }
        } catch (Throwable ignored) {
            // fall back to reflection
        }

        if (properties.isEmpty()) {
            for (java.lang.reflect.Parameter p : ft.func().getParameters()) {
                String name = p.getName();
                Map<String, Object> propSchema = new LinkedHashMap<>();
                propSchema.put("type", jsonTypeOf(p.getType()));
                properties.put(name, propSchema);
                required.add(name);
            }
        }

        schema.put("properties", properties);
        if (!required.isEmpty()) schema.put("required", required);
        return schema;
    }

    private static Map<String, Object> schemaToMap(Schema s) {
        Map<String, Object> m = new LinkedHashMap<>();
        s.type().ifPresent(t -> m.put("type", t.toString().toLowerCase()));
        s.description().ifPresent(d -> m.put("description", d));
        return m;
    }

    private static String jsonTypeOf(Class<?> type) {
        if (type == String.class) return "string";
        if (type == int.class || type == Integer.class
            || type == long.class || type == Long.class) return "integer";
        if (type == double.class || type == Double.class
            || type == float.class || type == Float.class) return "number";
        if (type == boolean.class || type == Boolean.class) return "boolean";
        if (type.isArray() || List.class.isAssignableFrom(type)) return "array";
        return "object";
    }

    private static Object[] buildArgs(Method method, Map<String, Object> inputData) {
        java.lang.reflect.Parameter[] params = method.getParameters();
        Object[] args = new Object[params.length];
        for (int i = 0; i < params.length; i++) {
            String pn = params[i].getName();
            Object raw = inputData != null ? inputData.get(pn) : null;
            args[i] = coerce(raw, params[i].getType());
        }
        return args;
    }

    private static Object coerce(Object value, Class<?> type) {
        if (value == null) {
            if (type == int.class) return 0;
            if (type == long.class) return 0L;
            if (type == double.class) return 0.0;
            if (type == boolean.class) return false;
            return null;
        }
        if (type.isInstance(value)) return value;
        String s = value.toString();
        if (type == String.class) return s;
        if (type == int.class || type == Integer.class) {
            return value instanceof Number n ? n.intValue() : Integer.parseInt(s);
        }
        if (type == long.class || type == Long.class) {
            return value instanceof Number n ? n.longValue() : Long.parseLong(s);
        }
        if (type == double.class || type == Double.class) {
            return value instanceof Number n ? n.doubleValue() : Double.parseDouble(s);
        }
        if (type == boolean.class || type == Boolean.class) {
            return value instanceof Boolean b ? b : Boolean.parseBoolean(s);
        }
        return value;
    }
}
