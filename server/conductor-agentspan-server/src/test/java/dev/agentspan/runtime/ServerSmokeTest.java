/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime;

import static org.assertj.core.api.Assertions.*;

import java.net.HttpURLConnection;
import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

/**
 * Boots the full Spring context and verifies /api/agent/list responds 200.
 * Must stay green before and after the multi-module restructure (Phase 0).
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class ServerSmokeTest {

    @LocalServerPort
    int port;

    @Test
    void agentListEndpointResponds200() throws Exception {
        var url = URI.create("http://localhost:" + port + "/api/agent/list").toURL();
        var conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("GET");
        assertThat(conn.getResponseCode()).isEqualTo(200);
        conn.disconnect();
    }
}
