/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import java.util.*;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;

/**
 * Normalizes Claude Agent SDK rawConfig into a passthrough AgentConfig.
 */
@Component
public class ClaudeAgentSdkNormalizer implements AgentConfigNormalizer {

    private static final Logger log = LoggerFactory.getLogger(ClaudeAgentSdkNormalizer.class);
    private static final String DEFAULT_NAME = "claude_agent_sdk_agent";

    @Override
    public String frameworkId() {
        return "claude_agent_sdk";
    }

    @Override
    public AgentConfig normalize(Map<String, Object> raw) {
        String name = getString(raw, "name", DEFAULT_NAME);
        String workerName = getString(raw, "_worker_name", name);
        log.info("Normalizing Claude Agent SDK agent: {}", name);

        AgentConfig config = new AgentConfig();
        config.setName(name);

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("_framework_passthrough", true);
        config.setMetadata(metadata);

        ToolConfig worker = ToolConfig.builder()
                .name(workerName)
                .description("Claude Agent SDK passthrough worker")
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
