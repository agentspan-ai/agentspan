/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.util.Map;

import org.hamcrest.Matchers;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import dev.agentspan.runtime.AgentRuntime;
import dev.agentspan.runtime.credentials.CredentialStoreProvider;
import dev.agentspan.runtime.model.AgentExecutionDetail;
import dev.agentspan.runtime.service.AgentService;

/**
 * Verifies that {@link CredentialMaskingResponseAdvice} activates on the right
 * URI patterns and leaves the payload unchanged in OSS (no-op masker — disclosure
 * tracking is an enterprise feature).
 *
 * <p>Masking-correctness tests (redaction, tree-walk, JSON-escape handling) live
 * in the enterprise module where the real {@link dev.agentspan.runtime.credentials.CredentialOutputMasker}
 * implementation is provided.</p>
 */
@SpringBootTest(classes = AgentRuntime.class)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class CredentialMaskingIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private CredentialStoreProvider store;

    @MockBean
    private AgentService agentService;

    private static final String CRED_NAME = "_MASK_E2E_TOKEN";
    private static final String CRED_VALUE = "ghp_thisisasecretthatshouldbemasked";
    private static final String EXEC_ID = "exec-mask-e2e-001";
    private static final String userId = "00000000-0000-0000-0000-000000000000";

    @BeforeEach
    void setUp() {
        store.set(userId, CRED_NAME, CRED_VALUE);
    }

    @AfterEach
    void cleanUp() {
        store.delete(userId, CRED_NAME);
    }

    // ── Advice URI coverage ─────────────────────────────────────────────

    @Test
    void executionDetail_adviceActivates_passesThrough() throws Exception {
        // In OSS the masker is a no-op: value passes through unchanged.
        // This test confirms the advice activates on /api/agent/executions/{id}
        // without throwing and without blocking the response.
        AgentExecutionDetail detail = AgentExecutionDetail.builder()
                .executionId(EXEC_ID)
                .agentName("test-agent")
                .status("COMPLETED")
                .output(Map.of("result", "token is " + CRED_VALUE))
                .build();
        when(agentService.getExecutionDetail(eq(EXEC_ID))).thenReturn(detail);

        mvc.perform(get("/api/agent/executions/" + EXEC_ID))
                .andExpect(status().isOk())
                // OSS no-op: value is still present (masking is enterprise)
                .andExpect(content().string(Matchers.containsString(CRED_VALUE)));
    }

    @Test
    void statusEndpoint_adviceActivates_passesThrough() throws Exception {
        when(agentService.getStatus(eq(EXEC_ID)))
                .thenReturn(Map.of("executionId", EXEC_ID, "status", "COMPLETED", "note", "token=" + CRED_VALUE));

        mvc.perform(get("/api/agent/" + EXEC_ID + "/status"))
                .andExpect(status().isOk())
                .andExpect(content().string(Matchers.containsString(CRED_VALUE)));
    }

    @Test
    void getCredential_endpointNotIntercepted() throws Exception {
        // /api/secrets/{key} is the CRUD endpoint — the advice must NOT
        // intercept it regardless of what credentials are in the store.
        mvc.perform(get("/api/secrets/" + CRED_NAME))
                .andExpect(status().isOk())
                .andExpect(content().string(CRED_VALUE));
    }
}
