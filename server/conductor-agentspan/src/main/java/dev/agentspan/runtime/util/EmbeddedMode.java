/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Captures whether AgentSpan is running embedded in a host (e.g. orkes-conductor) into a static
 * flag, so compile-time code reached through plain (non-Spring) helpers — e.g. {@code ToolCompiler}
 * — can branch on it. Populated once at startup from the {@code agentspan.embedded} property
 * (default {@code false} for the standalone server). Compilation is request-driven, so the value is
 * always set before any compile runs.
 */
@Component
public class EmbeddedMode {

    private static volatile boolean embedded = false;

    @Value("${agentspan.embedded:false}")
    public void setEmbedded(boolean value) {
        embedded = value;
    }

    public static boolean isEmbedded() {
        return embedded;
    }
}
