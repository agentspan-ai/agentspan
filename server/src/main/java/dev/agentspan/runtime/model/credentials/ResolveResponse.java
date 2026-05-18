/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.model.credentials;

import java.util.Map;

import lombok.Builder;
import lombok.Data;

/** Response body for POST /api/credentials/resolve */
@Data
@Builder
public class ResolveResponse {
    private Map<String, String> credentials; // name → plaintext value
}
