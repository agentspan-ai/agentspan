/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.DependsOn;
import org.springframework.stereotype.Component;

/**
 * Seeds users from agentspan.auth.users[] properties at startup.
 * Uses createIfNotExists to avoid overwriting user-changed passwords.
 */
@Component
@DependsOn("credentialSchemaInitializer")
public class AuthUserSeeder {

    private static final Logger log = LoggerFactory.getLogger(AuthUserSeeder.class);

    private final UserRepository userRepository;
    private final AuthProperties authProperties;

    public AuthUserSeeder(UserRepository userRepository, AuthProperties authProperties) {
        this.userRepository = userRepository;
        this.authProperties = authProperties;
    }

    @PostConstruct
    public void seed() {
        for (AuthProperties.UserEntry entry : authProperties.getUsers()) {
            String name = entry.getName() != null ? entry.getName() : entry.getUsername();
            userRepository.createIfNotExists(
                entry.getUsername(), name, entry.getEmail(), entry.getPassword());
            log.info("Ensured user exists: {}", entry.getUsername());
        }
    }
}
