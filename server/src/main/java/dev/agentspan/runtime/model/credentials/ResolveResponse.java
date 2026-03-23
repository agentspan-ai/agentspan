/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.model.credentials;

import lombok.Builder;
import lombok.Data;
import java.util.Map;

/** Response body for POST /api/credentials/resolve */
@Data
@Builder
public class ResolveResponse {
    private Map<String, String> credentials;  // name → plaintext value
}
