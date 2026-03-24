// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.internal;

import dev.agentspan.annotations.GuardrailDef;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.model.GuardrailResult;
import dev.agentspan.model.ToolContext;
import dev.agentspan.model.ToolDef;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Discovers {@link Tool} and {@link GuardrailDef} annotated methods via reflection.
 */
public class ToolRegistry {
    private static final Logger logger = LoggerFactory.getLogger(ToolRegistry.class);

    private ToolRegistry() {}

    /**
     * Discover all {@link Tool}-annotated methods on an object and return ToolDef instances.
     *
     * @param obj the object to inspect
     * @return list of ToolDef instances
     */
    public static List<ToolDef> fromInstance(Object obj) {
        List<ToolDef> tools = new ArrayList<>();
        for (Method method : obj.getClass().getMethods()) {
            Tool ann = method.getAnnotation(Tool.class);
            if (ann == null) continue;

            String name = ann.name().isEmpty() ? method.getName() : ann.name();
            Map<String, Object> schema = generateSchema(method);

            method.setAccessible(true);
            Function<Map<String, Object>, Object> func = inputData -> {
                try {
                    Object[] methodArgs = buildMethodArgs(method, inputData, null);
                    return method.invoke(obj, methodArgs);
                } catch (Exception e) {
                    throw new RuntimeException("Tool execution failed: " + name, e);
                }
            };

            List<String> credentials = Arrays.asList(ann.credentials());

            tools.add(new ToolDef.Builder()
                .name(name)
                .description(ann.description())
                .inputSchema(schema)
                .func(func)
                .approvalRequired(ann.approvalRequired())
                .timeoutSeconds(ann.timeoutSeconds())
                .toolType("worker")
                .credentials(credentials)
                .build());

            logger.debug("Registered tool '{}' from {}", name, obj.getClass().getSimpleName());
        }
        return tools;
    }

    /**
     * Discover all {@link GuardrailDef}-annotated methods on an object and return guardrail definitions.
     *
     * @param obj the object to inspect
     * @return list of dev.agentspan.model.GuardrailDef instances
     */
    public static List<dev.agentspan.model.GuardrailDef> guardrailsFromInstance(Object obj) {
        List<dev.agentspan.model.GuardrailDef> guardrails = new ArrayList<>();
        for (Method method : obj.getClass().getMethods()) {
            GuardrailDef ann = method.getAnnotation(GuardrailDef.class);
            if (ann == null) continue;

            String name = ann.name().isEmpty() ? method.getName() : ann.name();

            method.setAccessible(true);
            Function<String, GuardrailResult> func = input -> {
                try {
                    return (GuardrailResult) method.invoke(obj, input);
                } catch (Exception e) {
                    throw new RuntimeException("Guardrail execution failed: " + name, e);
                }
            };

            guardrails.add(new dev.agentspan.model.GuardrailDef.Builder()
                .name(name)
                .position(ann.position())
                .onFail(ann.onFail())
                .maxRetries(ann.maxRetries())
                .func(func)
                .guardrailType("custom")
                .build());

            logger.debug("Registered guardrail '{}' from {}", name, obj.getClass().getSimpleName());
        }
        return guardrails;
    }

    /**
     * Build the JSON Schema for the given method's parameters.
     */
    public static Map<String, Object> generateSchema(Method method) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        Map<String, Object> props = new LinkedHashMap<>();
        List<String> required = new ArrayList<>();

        for (Parameter param : method.getParameters()) {
            // Skip ToolContext parameters
            if (param.getType() == ToolContext.class) continue;

            Map<String, Object> propSchema = typeToJsonSchema(param.getType());
            props.put(param.getName(), propSchema);
            required.add(param.getName());
        }

        schema.put("properties", props);
        if (!required.isEmpty()) {
            schema.put("required", required);
        }
        return schema;
    }

    /**
     * Convert a Java type to a JSON Schema type descriptor.
     */
    public static Map<String, Object> typeToJsonSchema(Class<?> type) {
        Map<String, Object> schema = new LinkedHashMap<>();
        if (type == String.class) {
            schema.put("type", "string");
        } else if (type == int.class || type == Integer.class
                || type == long.class || type == Long.class) {
            schema.put("type", "integer");
        } else if (type == double.class || type == Double.class
                || type == float.class || type == Float.class) {
            schema.put("type", "number");
        } else if (type == boolean.class || type == Boolean.class) {
            schema.put("type", "boolean");
        } else if (Map.class.isAssignableFrom(type)) {
            schema.put("type", "object");
        } else if (List.class.isAssignableFrom(type)
                || type.isArray()) {
            schema.put("type", "array");
        } else {
            schema.put("type", "object");
        }
        return schema;
    }

    /**
     * Build the argument array for invoking a method with input data from the server.
     *
     * <p>Supports both named parameters (when compiled with -parameters) and positional
     * parameters (when compiled without -parameters, arg0/arg1/...).
     *
     * @param method    the method to invoke
     * @param inputData the input map from the server
     * @param context   optional ToolContext
     * @return array of arguments in method parameter order
     */
    private static Object[] buildMethodArgs(Method method, Map<String, Object> inputData, ToolContext context) {
        Parameter[] params = method.getParameters();
        Object[] args = new Object[params.length];

        // Collect non-context parameter values in order
        List<Object> inputValues = null;
        if (inputData != null && !inputData.isEmpty()) {
            // Check if params have real names (compiled with -parameters)
            boolean hasRealNames = params.length > 0
                && !params[0].getName().equals("arg0")
                && !params[0].getName().startsWith("arg");

            if (!hasRealNames) {
                // Fall back to positional: use values in iteration order
                inputValues = new ArrayList<>(inputData.values());
            }
        }

        int dataIndex = 0;
        for (int i = 0; i < params.length; i++) {
            Parameter param = params[i];
            if (param.getType() == ToolContext.class) {
                args[i] = context;
                continue;
            }

            Object raw;
            if (inputData == null) {
                raw = null;
            } else if (inputValues != null) {
                // Positional lookup
                raw = dataIndex < inputValues.size() ? inputValues.get(dataIndex) : null;
                dataIndex++;
            } else {
                // Named lookup
                raw = inputData.get(param.getName());
            }
            args[i] = coerce(raw, param.getType());
        }

        return args;
    }

    /**
     * Coerce a raw value (typically from JSON deserialization) to the target Java type.
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
        // Fallback: try Jackson conversion for complex types
        try {
            return JsonMapper.get().convertValue(value, targetType);
        } catch (Exception e) {
            return value;
        }
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
