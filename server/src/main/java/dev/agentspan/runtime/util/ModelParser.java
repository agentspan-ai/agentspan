/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import lombok.AllArgsConstructor;
import lombok.Data;

/**
 * Parses "provider/model" strings into provider and model components.
 * Mirrors python/src/conductor/agents/_internal/model_parser.py.
 */
public class ModelParser {

    @Data
    @AllArgsConstructor
    public static class ParsedModel {
        private String provider;
        private String model;
    }

    /**
     * Parse a model string like "openai/gpt-4o" into provider and model.
     *
     * @param modelString The model string in "provider/model" format.
     * @return A ParsedModel with provider and model components.
     * @throws IllegalArgumentException if the format is invalid.
     */
    public static ParsedModel parse(String modelString) {
        if (modelString == null || modelString.isBlank()) {
            throw new IllegalArgumentException("Model string cannot be null or empty");
        }

        int slashIdx = modelString.indexOf('/');
        if (slashIdx <= 0 || slashIdx >= modelString.length() - 1) {
            throw new IllegalArgumentException(
                    "Invalid model format: '" + modelString + "'. Expected 'provider/model'.");
        }

        String provider = modelString.substring(0, slashIdx);
        String model = modelString.substring(slashIdx + 1);
        return new ParsedModel(provider, model);
    }
}
