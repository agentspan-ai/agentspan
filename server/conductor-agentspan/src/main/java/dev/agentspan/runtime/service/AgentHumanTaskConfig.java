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
 * Registers {@link AgentHumanTask} as the primary HUMAN task implementation,
 * overriding Conductor's default {@code Human} system task.
 *
 * <p><b>Embedded mode:</b> disabled when {@code agentspan.embedded=true} (e.g. when the
 * library is imported into a host such as orkes-conductor). The host provides its own
 * (richer) HUMAN task — overriding it here would collide on the {@code HUMAN} bean name and
 * replace the host's full HITL implementation with this SSE-only shim. The host is expected
 * to emit the {@code WAITING} SSE event from its own HUMAN task, guarded by the
 * {@code __agentspan_ctx__} input. The standalone OSS server leaves this property unset, so
 * the override stays active as before.</p>
 */
@Configuration
@ConditionalOnProperty(name = "agentspan.embedded", havingValue = "false", matchIfMissing = true)
public class AgentHumanTaskConfig {

    @Bean(TASK_TYPE_HUMAN)
    @Primary
    public AgentHumanTask agentHumanTask(AgentStreamRegistry streamRegistry) {
        return new AgentHumanTask(streamRegistry);
    }
}
