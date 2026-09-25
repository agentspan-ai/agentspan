/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import static com.netflix.conductor.common.metadata.tasks.TaskType.TASK_TYPE_HUMAN;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

/**
 * Registers {@link AgentHumanTask} as the {@code HUMAN} system task when running in
 * embedded mode ({@code agentspan.embedded=true}).
 *
 * <p>The {@code @Bean("HUMAN")} definition <em>overrides</em> Conductor's default
 * {@code Human} component (enabled via {@code spring.main.allow-bean-definition-overriding=true}),
 * so exactly one bean named {@code HUMAN} exists. This avoids the component-scan bean-name
 * collision and the duplicate taskType key in {@code SystemTaskRegistry} that would otherwise
 * result from having two {@code WorkflowSystemTask}s both reporting the {@code HUMAN} type.</p>
 *
 * <p>When {@code agentspan.embedded} is unset (the standalone OSS server), this configuration
 * is skipped and Conductor's default {@code Human} task remains in effect.</p>
 */
@Configuration
@ConditionalOnProperty(name = "agentspan.embedded", havingValue = "true")
public class AgentHumanTaskConfig {

    @Bean(TASK_TYPE_HUMAN)
    @Primary
    public AgentHumanTask agentHumanTask(AgentStreamRegistry streamRegistry) {
        return new AgentHumanTask(streamRegistry);
    }
}
