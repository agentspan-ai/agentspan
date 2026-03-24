/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.*;

/**
 * Normalizes Vercel AI SDK rawConfig into a passthrough AgentConfig.
 */
@Component
public class VercelAINormalizer implements AgentConfigNormalizer {

    private static final Logger log = LoggerFactory.getLogger(VercelAINormalizer.class);
    private static final String DEFAULT_NAME = "vercel_ai_agent";

    @Override
    public String frameworkId() {
        return "vercel_ai";
    }

    @Override
    public AgentConfig normalize(Map<String, Object> raw) {
        String name = getString(raw, "name", DEFAULT_NAME);
        String workerName = getString(raw, "_worker_name", name);
        log.info("Normalizing Vercel AI SDK agent: {}", name);

        AgentConfig config = new AgentConfig();
        config.setName(name);

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("_framework_passthrough", true);
        config.setMetadata(metadata);

        ToolConfig worker = ToolConfig.builder()
            .name(workerName)
            .description("Vercel AI SDK passthrough worker")
            .toolType("worker")
            .build();
        config.setTools(List.of(worker));

        return config;
    }

    private String getString(Map<String, Object> map, String key, String defaultValue) {
        Object v = map.get(key);
        return v instanceof String ? (String) v : defaultValue;
    }
}
