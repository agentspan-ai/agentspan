/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import java.io.IOException;
import java.time.Instant;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import dev.agentspan.runtime.context.RequestContext;
import dev.agentspan.runtime.context.RequestContextHolder;

/**
 * Populates {@link RequestContextHolder} with an anonymous principal id on every request.
 * AgentSpan is single-tenant by default; an embedding application (e.g. orkes-conductor) is
 * responsible for supplying its own principal adapter instead of this filter.
 */
@Component
public class AuthFilter extends OncePerRequestFilter {

    /** Matches {@code CredentialEnvSeeder.ANONYMOUS_USER_ID}. */
    static final String ANONYMOUS_USER_ID = "00000000-0000-0000-0000-000000000000";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        try {
            RequestContextHolder.set(RequestContext.builder()
                    .requestId(UUID.randomUUID().toString())
                    .userId(ANONYMOUS_USER_ID)
                    .createdAt(Instant.now())
                    .build());
            chain.doFilter(request, response);
        } finally {
            RequestContextHolder.clear();
        }
    }
}
