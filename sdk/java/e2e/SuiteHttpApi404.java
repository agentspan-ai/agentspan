// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.AgentConfig;
import ai.agentspan.exceptions.AgentAPIException;
import ai.agentspan.exceptions.AgentNotFoundException;
import ai.agentspan.exceptions.AgentspanException;
import ai.agentspan.internal.HttpApi;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Live 404 round-trip — proves HttpApi maps server 404 responses to the
 * narrower {@link AgentNotFoundException} subtype (Python-SDK parity).
 *
 * <p>Counterfactual: if HttpApi raised the generic {@link AgentAPIException}
 * for every 4xx (the pre-refactor behavior), the {@code assertInstanceOf}
 * check below would fail.
 */
@Tag("e2e")
class SuiteHttpApi404 extends BaseTest {

    @Test
    void getStatusOnMissingExecutionIdRaisesAgentNotFoundException() {
        HttpApi api = new HttpApi(new AgentConfig(BASE_URL, null, null, 100, 1));

        AgentAPIException ex = assertThrows(
            AgentAPIException.class,
            () -> api.getAgentStatus("does-not-exist-" + System.nanoTime())
        );

        assertInstanceOf(AgentNotFoundException.class, ex,
            "404 must surface as AgentNotFoundException, not generic AgentAPIException");
        assertInstanceOf(AgentspanException.class, ex,
            "AgentNotFoundException must remain catchable as the SDK base type");
        assertTrue(ex.getStatusCode() == 404,
            "Expected statusCode=404, got " + ex.getStatusCode());
    }
}
