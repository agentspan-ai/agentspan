/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Pure identity record. Authorization (roles, RBAC) is handled by the
 * enterprise module — it is not part of User.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class User {
    private String id; // UUID — OIDC sub claim, or internal DB id
    private String name; // display name
    private String email;
    private String username;
}
