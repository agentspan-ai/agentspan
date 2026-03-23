/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AuthFilterTest {

    @Mock private UserRepository userRepository;
    @Mock private ApiKeyRepository apiKeyRepository;
    @Mock private HttpServletRequest request;
    @Mock private HttpServletResponse response;
    @Mock private FilterChain chain;

    private AuthFilter filter;
    private PrintWriter responseWriter;

    @BeforeEach
    void setUp() throws Exception {
        filter = new AuthFilter(userRepository, apiKeyRepository, true /* auth enabled */);
        responseWriter = new PrintWriter(new StringWriter());
        lenient().when(response.getWriter()).thenReturn(responseWriter);
    }

    @AfterEach
    void tearDown() {
        RequestContextHolder.clear();
    }

    @Test
    void authDisabled_populatesAnonymousContext() throws Exception {
        AuthFilter anonFilter = new AuthFilter(userRepository, apiKeyRepository, false);
        AtomicReference<RequestContext> capturedCtx = new AtomicReference<>();

        doAnswer(invocation -> {
            capturedCtx.set(RequestContextHolder.get().orElse(null));
            return null;
        }).when(chain).doFilter(request, response);

        anonFilter.doFilterInternal(request, response, chain);

        verify(chain).doFilter(request, response);
        assertThat(capturedCtx.get()).isNotNull();
        assertThat(capturedCtx.get().getUser().getUsername()).isEqualTo("anonymous");
    }

    @Test
    void noCredentials_returnsUnauthorized() throws Exception {
        when(request.getHeader("X-API-Key")).thenReturn(null);
        when(request.getHeader("Authorization")).thenReturn(null);

        filter.doFilterInternal(request, response, chain);

        verify(response).setStatus(401);
        verify(chain, never()).doFilter(any(), any());
    }

    @Test
    void validApiKey_populatesContext() throws Exception {
        User bob = new User("u2", "Bob", "bob@test.com", "bob");
        when(request.getHeader("X-API-Key")).thenReturn("asp_testkey");
        when(apiKeyRepository.findUserByKey("asp_testkey")).thenReturn(Optional.of(bob));
        AtomicReference<RequestContext> capturedCtx = new AtomicReference<>();

        doAnswer(invocation -> {
            capturedCtx.set(RequestContextHolder.get().orElse(null));
            return null;
        }).when(chain).doFilter(request, response);

        filter.doFilterInternal(request, response, chain);

        verify(chain).doFilter(request, response);
        assertThat(capturedCtx.get()).isNotNull();
        assertThat(capturedCtx.get().getUser().getUsername()).isEqualTo("bob");
    }

    @Test
    void invalidApiKey_returns401() throws Exception {
        when(request.getHeader("X-API-Key")).thenReturn("asp_badkey");
        when(apiKeyRepository.findUserByKey("asp_badkey")).thenReturn(Optional.empty());

        filter.doFilterInternal(request, response, chain);

        verify(response).setStatus(401);
        verify(chain, never()).doFilter(any(), any());
    }

    @Test
    void contextIsCleared_afterRequest() throws Exception {
        User user = new User("u3", "Carol", null, "carol");
        when(request.getHeader("X-API-Key")).thenReturn("asp_carol");
        when(apiKeyRepository.findUserByKey("asp_carol")).thenReturn(Optional.of(user));

        filter.doFilterInternal(request, response, chain);

        // After the filter completes, the context must be cleared
        assertThat(RequestContextHolder.get()).isEmpty();
    }

    @Test
    void loginEndpoint_isAllowedWithoutAuthentication() throws Exception {
        // shouldNotFilter() must return true for /api/auth/login so the filter
        // never blocks the login endpoint (even when auth is enabled).
        when(request.getServletPath()).thenReturn("/api/auth/login");
        assertThat(filter.shouldNotFilter(request)).isTrue();
    }

    @Test
    void nonLoginEndpoint_isNotExemptFromFilter() throws Exception {
        when(request.getServletPath()).thenReturn("/api/credentials");
        assertThat(filter.shouldNotFilter(request)).isFalse();
    }
}
