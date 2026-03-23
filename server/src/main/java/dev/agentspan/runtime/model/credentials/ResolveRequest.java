/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.model.credentials;

import lombok.Data;
import java.util.List;

/** Request body for POST /api/credentials/resolve */
@Data
public class ResolveRequest {
    private String token;
    private List<String> names;
}
