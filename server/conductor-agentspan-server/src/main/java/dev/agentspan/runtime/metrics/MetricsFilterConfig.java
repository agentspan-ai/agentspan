/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.metrics;

import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;

/**
 * Filters out Conductor internal metrics from the Prometheus endpoint.
 *
 * <p>Conductor publishes low-level task/workflow execution metrics (queue depth,
 * poll counts, sweeper timing, etc.) that are not useful for agent-level
 * dashboards. This filter denies them so only agentspan and standard Spring
 * Boot / JVM metrics are exposed.</p>
 */
@Configuration
public class MetricsFilterConfig {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> denyConductorMetrics() {
        return registry -> registry.config()
                .meterFilter(MeterFilter.denyNameStartsWith("task_"))
                .meterFilter(MeterFilter.denyNameStartsWith("tasks_"))
                .meterFilter(MeterFilter.denyNameStartsWith("workflow_"))
                .meterFilter(MeterFilter.denyNameStartsWith("workflowSweeper"))
                .meterFilter(MeterFilter.denyNameStartsWith("system_task_worker"));
    }
}
