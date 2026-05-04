// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.internal;

import ai.agentspan.annotations.GuardrailDef;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.OnFail;
import ai.agentspan.enums.Position;
import ai.agentspan.model.GuardrailResult;
import ai.agentspan.model.ToolContext;
import ai.agentspan.model.ToolDef;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
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
                    // Extract persisted state injected by the server
                    Map<String, Object> agentState = new java.util.HashMap<>();
                    if (inputData != null) {
                        Object stateRaw = inputData.get("_agent_state");
                        if (stateRaw instanceof Map) {
                            @SuppressWarnings("unchecked")
                            Map<String, Object> stateMap = (Map<String, Object>) stateRaw;
                            agentState.putAll(stateMap);
                        }
                    }

                    ToolContext context = new ToolContext(null, null, null, agentState);
                    Object[] methodArgs = buildMethodArgs(method, inputData, context);
                    Object result = method.invoke(obj, methodArgs);

                    // If state was mutated, include _state_updates in the output
                    if (!context.getState().isEmpty()) {
                        Map<String, Object> output = new java.util.LinkedHashMap<>();
                        if (result instanceof Map) {
                            @SuppressWarnings("unchecked")
                            Map<String, Object> resultMap = (Map<String, Object>) result;
                            output.putAll(resultMap);
                        } else if (result != null) {
                            output.put("result", result);
                        }
                        output.put("_state_updates", context.getState());
                        return output;
                    }
                    return result;
                } catch (Exception e) {
                    throw new RuntimeException("Tool execution failed: " + name, e);
                }
            };

            List<String> credentials = Arrays.asList(ann.credentials());
            Map<String, Object> outputSchema = typeToJsonSchema(method.getReturnType());

            tools.add(new ToolDef.Builder()
                .name(name)
                .description(ann.description())
                .inputSchema(schema)
                .outputSchema(outputSchema)
                .func(func)
                .approvalRequired(ann.approvalRequired())
                .timeoutSeconds(ann.timeoutSeconds())
                .maxCalls(ann.maxCalls())
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
     * @return list of ai.agentspan.model.GuardrailDef instances
     */
    public static List<ai.agentspan.model.GuardrailDef> guardrailsFromInstance(Object obj) {
        List<ai.agentspan.model.GuardrailDef> guardrails = new ArrayList<>();
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

            guardrails.add(new ai.agentspan.model.GuardrailDef.Builder()
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

            Map<String, Object> propSchema = typeToJsonSchema(param.getParameterizedType());
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
     * Convert a Java generic type (including parameterized types like {@code List<Double>})
     * to a JSON Schema type descriptor.
     */
    public static Map<String, Object> typeToJsonSchema(Type type) {
        if (type instanceof ParameterizedType) {
            ParameterizedType pt = (ParameterizedType) type;
            Class<?> raw = (Class<?>) pt.getRawType();
            if (List.class.isAssignableFrom(raw)) {
                Map<String, Object> schema = new LinkedHashMap<>();
                schema.put("type", "array");
                Type[] typeArgs = pt.getActualTypeArguments();
                if (typeArgs.length > 0) {
                    schema.put("items", typeToJsonSchema(typeArgs[0]));
                }
                return schema;
            }
            return typeToJsonSchema(raw);
        } else if (type instanceof Class) {
            return typeToJsonSchema((Class<?>) type);
        }
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
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
            schema.put("additionalProperties", new java.util.LinkedHashMap<>());
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
            args[i] = coerce(raw, param.getType(), param.getParameterizedType());
        }

        return args;
    }

    /**
     * Coerce a raw value (typically from JSON deserialization) to the target Java type.
     */
    private static Object coerce(Object value, Class<?> targetType) {
        return coerce(value, targetType, targetType);
    }

    /**
     * Coerce a raw value to the target Java type, using full generic type info when available.
     * This handles e.g. {@code List<Double>} where the raw type is just {@code List.class}.
     */
    private static Object coerce(Object value, Class<?> targetType, Type genericType) {
        if (value == null) return defaultFor(targetType);

        // For collections, always go through Jackson with the full parameterized type so that
        // element types are correctly coerced. Without this, JSON integers arrive as Integer
        // even when the method signature declares List<Double>.
        if (List.class.isAssignableFrom(targetType)) {
            try {
                com.fasterxml.jackson.databind.type.TypeFactory tf =
                    JsonMapper.get().getTypeFactory();
                com.fasterxml.jackson.databind.JavaType jt = (genericType != null)
                    ? tf.constructType(genericType)
                    : tf.constructCollectionType(List.class, Object.class);
                return JsonMapper.get().convertValue(value, jt);
            } catch (Exception e) {
                return value;
            }
        }

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
            com.fasterxml.jackson.databind.JavaType jt = (genericType != null)
                ? JsonMapper.get().getTypeFactory().constructType(genericType)
                : JsonMapper.get().getTypeFactory().constructType(targetType);
            return JsonMapper.get().convertValue(value, jt);
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
