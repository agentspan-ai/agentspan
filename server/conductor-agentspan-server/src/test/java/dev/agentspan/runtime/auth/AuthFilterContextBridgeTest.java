/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

import java.util.concurrent.atomic.AtomicReference;

import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import dev.agentspan.runtime.context.RequestContextHolder;

/**
 * The request-filter → context bridge.
 *
 * <p>Every other test sets {@code RequestContextHolder} by hand. This one asserts the filter that
 * actually populates it at the HTTP edge does its job: a principal is present <em>during</em> the
 * chain, and the thread-local is <em>always</em> cleared afterwards.</p>
 *
 * <p>The clear-on-exception case is the security-relevant one: request threads are pooled, so a
 * context that survives a failed request would bind the next request on that thread to the previous
 * caller's identity. The {@code finally} block in {@link AuthFilter} is what prevents that.</p>
 *
 * <p>(The embed-mode host bridge — a host-supplied principal adapter replacing this filter — is the
 * part still gated on §6 engine coordinates; this covers the standalone filter that ships today.)</p>
 */
class AuthFilterContextBridgeTest {

    private final AuthFilter filter = new AuthFilter();

    @AfterEach
    void tearDown() {
        // Defensive: ensure no leak escapes the test itself regardless of outcome.
        RequestContextHolder.clear();
    }

    @Test
    void populatesAnonymousPrincipalDuringChain_andClearsAfter() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        HttpServletResponse response = mock(HttpServletResponse.class);

        AtomicReference<String> userIdDuringChain = new AtomicReference<>();
        FilterChain chain = (req, res) ->
                userIdDuringChain.set(RequestContextHolder.getRequiredUserId());

        filter.doFilterInternal(request, response, chain);

        // During the chain the anonymous principal was present...
        assertThat(userIdDuringChain.get()).isEqualTo(AuthFilter.ANONYMOUS_USER_ID);
        // ...and the thread-local is cleared once the request unwinds.
        assertThat(RequestContextHolder.get()).isEmpty();
    }

    @Test
    void clearsContext_evenWhenChainThrows() {
        HttpServletRequest request = mock(HttpServletRequest.class);
        HttpServletResponse response = mock(HttpServletResponse.class);

        FilterChain boom = (req, res) -> {
            // Sanity: context is set before the downstream blows up.
            assertThat(RequestContextHolder.get()).isPresent();
            throw new RuntimeException("downstream failure");
        };

        assertThatThrownBy(() -> filter.doFilterInternal(request, response, boom))
                .isInstanceOf(RuntimeException.class)
                .hasMessage("downstream failure");

        // The finally block must have cleared the context so a pooled thread
        // can't carry this request's identity into the next one.
        assertThat(RequestContextHolder.get()).isEmpty();
    }
}
