/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.config;

import jakarta.annotation.PostConstruct;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Configuration;

import dev.agentspan.runtime.service.AgentStreamRegistry;

/**
 * Registers a JVM shutdown hook (runs on SIGINT / SIGTERM only) that
 * completes SSE emitters and force-halts the JVM if conductor-core's
 * non-daemon threads (e.g. WorkflowSweeper) don't stop in time.
 */
@Configuration
public class ShutdownConfig {

    private static final Logger logger = LoggerFactory.getLogger(ShutdownConfig.class);
    private static final int FORCE_HALT_DELAY_SECONDS = 5;

    private final AgentStreamRegistry streamRegistry;

    public ShutdownConfig(AgentStreamRegistry streamRegistry) {
        this.streamRegistry = streamRegistry;
    }

    @PostConstruct
    public void registerShutdownHook() {
        Runtime.getRuntime()
                .addShutdownHook(new Thread(
                        () -> {
                            logger.info("Shutdown signal received — completing SSE emitters");
                            try {
                                streamRegistry.completeAll();
                            } catch (Exception e) {
                                logger.warn("Exception completing SSE emitters during shutdown: {}", e.getMessage());
                            }

                            // Conductor-core's WorkflowSweeper runs in a non-daemon thread with a
                            // tight pollAndSweep loop that ignores interruption. Spring's
                            // ExecutorService.close() waits forever for it. Force-halt as a safety net.
                            try {
                                Thread.sleep(FORCE_HALT_DELAY_SECONDS * 1000L);
                                logger.warn(
                                        "Forcing JVM halt — conductor-core threads did not stop within {}s",
                                        FORCE_HALT_DELAY_SECONDS);
                                Runtime.getRuntime().halt(0);
                            } catch (InterruptedException e) {
                                // Normal shutdown completed before timeout — good
                            }
                        },
                        "agent-runtime-shutdown"));
    }
}
