/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import lombok.Data;

/**
 * Binds agentspan.auth.* from application.properties.
 * Default users are seeded at startup by AuthUserSeeder.
 */
@Data
@Component
@ConfigurationProperties(prefix = "agentspan.auth")
public class AuthProperties {

    /** Whether auth is enabled. When false, every request gets anonymous admin access. */
    private boolean enabled = true;

    /** List of users to seed at startup. Plain-text passwords are bcrypt-hashed on write. */
    private List<UserEntry> users = new ArrayList<>();

    @Data
    public static class UserEntry {
        private String username;
        private String password;
        private String name;
        private String email;
    }
}
