/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.model.secrets;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/** Key/value tag attached to a secret. Mirrors Conductor's Tag shape. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Tag {
    private String key;
    private String value;
}
