// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.exceptions;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.Test;

/** Pure unit tests for the SDK exception hierarchy (status/message/typed fields). */
class ExceptionsTest {

    @Test
    void agentApiCarriesStatusAndBody() {
        AgentAPIException e = new AgentAPIException(500, "boom");
        assertEquals(500, e.getStatusCode());
        assertEquals("boom", e.getResponseBody());
        assertInstanceOf(AgentspanException.class, e);
    }

    @Test
    void notFoundIsApiExceptionWith404() {
        AgentNotFoundException e = new AgentNotFoundException(404, "missing");
        assertEquals(404, e.getStatusCode());
        assertInstanceOf(AgentAPIException.class, e);
        assertInstanceOf(AgentspanException.class, e);
    }

    @Test
    void credentialNotFoundListsMissingNames() {
        CredentialNotFoundException e = new CredentialNotFoundException(List.of("A", "B"));
        assertEquals(List.of("A", "B"), e.getMissingNames());
        CredentialNotFoundException single = new CredentialNotFoundException("ONLY");
        assertTrue(single.getMissingNames().contains("ONLY"));
    }

    @Test
    void credentialServiceCarriesStatus() {
        assertEquals(503, new CredentialServiceException(503, "down").getStatusCode());
    }

    @Test
    void credentialAuthAndRateLimitAreAgentspanExceptions() {
        assertInstanceOf(AgentspanException.class, new CredentialAuthException("rejected"));
        assertInstanceOf(AgentspanException.class, new CredentialRateLimitException());
    }

    @Test
    void baseExceptionKeepsMessageAndCause() {
        Throwable cause = new IllegalStateException("c");
        AgentspanException e = new AgentspanException("m", cause);
        assertEquals("m", e.getMessage());
        assertSame(cause, e.getCause());
    }
}
