// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.internal;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Map;

/**
 * Singleton ObjectMapper factory with consistent configuration.
 */
public class JsonMapper {
    private static final ObjectMapper INSTANCE;

    static {
        INSTANCE = new ObjectMapper();
        INSTANCE.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        INSTANCE.setSerializationInclusion(JsonInclude.Include.NON_NULL);
    }

    private JsonMapper() {}

    /** Get the shared ObjectMapper instance. */
    public static ObjectMapper get() {
        return INSTANCE;
    }

    /**
     * Convert any object to a Map<String, Object> using Jackson.
     *
     * @param obj the object to convert
     * @return the object as a map
     */
    @SuppressWarnings("unchecked")
    public static Map<String, Object> toMap(Object obj) {
        return INSTANCE.convertValue(obj, Map.class);
    }

    /**
     * Serialize an object to a JSON string.
     *
     * @param obj the object to serialize
     * @return JSON string
     */
    public static String toJson(Object obj) {
        try {
            return INSTANCE.writeValueAsString(obj);
        } catch (Exception e) {
            throw new RuntimeException("Failed to serialize to JSON", e);
        }
    }

    /**
     * Deserialize a JSON string to the given type.
     *
     * @param json the JSON string
     * @param cls  the target class
     * @param <T>  the target type
     * @return the deserialized object
     */
    public static <T> T fromJson(String json, Class<T> cls) {
        try {
            return INSTANCE.readValue(json, cls);
        } catch (Exception e) {
            throw new RuntimeException("Failed to deserialize JSON", e);
        }
    }
}
