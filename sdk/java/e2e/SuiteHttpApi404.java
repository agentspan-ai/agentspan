// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.conductoross.conductor.ai.exceptions.AgentAPIException;
import org.conductoross.conductor.ai.exceptions.AgentNotFoundException;
import org.conductoross.conductor.ai.exceptions.AgentspanException;
import org.conductoross.conductor.ai.internal.AgentClient;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.netflix.conductor.client.http.ConductorClient;

import io.orkes.conductor.client.ApiClient;

/**
 * Live 404 round-trip — proves {@link AgentClient} maps server 404 responses
 * (raised by the Conductor client as {@code ConductorClientException}) to the
 * narrower {@link AgentNotFoundException} subtype (Python-SDK parity).
 *
 * <p>Counterfactual: if AgentClient raised the generic {@link AgentAPIException}
 * for every 4xx (or leaked Conductor's own exception), the {@code assertInstanceOf}
 * check below would fail.
 */
@Tag("e2e")
class SuiteHttpApi404 extends BaseTest {

    @Test
    void getStatusOnMissingExecutionIdRaisesAgentNotFoundException() {
        ConductorClient cc = new ApiClient(
                (BASE_URL.endsWith("/") ? BASE_URL.substring(0, BASE_URL.length() - 1) : BASE_URL) + "/api");
        AgentClient api = new AgentClient(cc);

        AgentAPIException ex =
                assertThrows(AgentAPIException.class, () -> api.getAgentStatus("does-not-exist-" + System.nanoTime()));

        assertInstanceOf(
                AgentNotFoundException.class,
                ex,
                "404 must surface as AgentNotFoundException, not generic AgentAPIException");
        assertInstanceOf(
                AgentspanException.class, ex, "AgentNotFoundException must remain catchable as the SDK base type");
        assertTrue(ex.getStatusCode() == 404, "Expected statusCode=404, got " + ex.getStatusCode());
    }
}
