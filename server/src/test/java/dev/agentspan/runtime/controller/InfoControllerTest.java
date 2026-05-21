/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

/**
 * Unit tests for {@link InfoController}.
 *
 * <p>The controller exposes a per-JVM ``instance_id`` so SDK clients can
 * detect server restarts and avoid re-syncing env vars on every script run.
 * The id must be stable for the life of the controller (same value across
 * calls) and present in the response body.</p>
 */
class InfoControllerTest {

    @Test
    void returnsInstanceIdInBody() {
        InfoController controller = new InfoController();

        ResponseEntity<Map<String, String>> resp = controller.info();

        assertThat(resp.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(resp.getBody()).isNotNull();
        assertThat(resp.getBody().get("instance_id"))
                .isNotNull()
                .isNotBlank();
    }

    @Test
    void instanceIdIsStableAcrossCalls() {
        InfoController controller = new InfoController();

        String first = controller.info().getBody().get("instance_id");
        String second = controller.info().getBody().get("instance_id");

        assertThat(second).isEqualTo(first);
    }

    @Test
    void differentControllersHaveDifferentInstanceIds() {
        // Each JVM start (≈ each controller construction in tests) gets a fresh id.
        InfoController a = new InfoController();
        InfoController b = new InfoController();

        String idA = a.info().getBody().get("instance_id");
        String idB = b.info().getBody().get("instance_id");

        assertThat(idA).isNotEqualTo(idB);
    }
}
