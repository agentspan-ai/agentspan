/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.util.List;
import java.util.Map;

import org.hamcrest.Matchers;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import dev.agentspan.runtime.AgentRuntime;
import dev.agentspan.runtime.model.AgentExecutionDetail;
import dev.agentspan.runtime.secrets.SecretDisclosureService;
import dev.agentspan.runtime.secrets.SecretStoreProvider;
import dev.agentspan.runtime.service.AgentService;

/**
 * End-to-end masking through the real HTTP pipeline. {@link AgentService} is mocked
 * so we can produce a deterministic response body containing the secret value;
 * everything else (the advice, the store, the disclosure DAO) is the real Spring bean.
 */
@SpringBootTest(classes = AgentRuntime.class)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class SecretMaskingIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private SecretStoreProvider store;

    @Autowired
    private SecretDisclosureService disclosures;

    @MockBean
    private AgentService agentService;

    @Autowired
    @Qualifier("secretJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String SECRET_NAME = "_MASK_E2E_TOKEN";
    private static final String SECRET_VALUE = "ghp_thisisasecretthatshouldbemasked";
    private static final String EXEC_ID = "exec-mask-e2e-001";

    // Anonymous user id used by AuthFilter when agentspan.auth.enabled=false (test profile).
    private static final String userId = "00000000-0000-0000-0000-000000000000";

    @BeforeEach
    void setUp() {
        store.set(userId, SECRET_NAME, SECRET_VALUE);
        disclosures.record(EXEC_ID, userId, List.of(SECRET_NAME));
    }

    @AfterEach
    void cleanUp() {
        store.delete(userId, SECRET_NAME);
        jdbc.update("DELETE FROM secret_disclosures WHERE user_id = :u", Map.of("u", userId));
    }

    @Test
    void getExecutionDetail_redactsSecretValueInOutput() throws Exception {
        // Build a detail response that "accidentally" contains the secret value
        // in the tool output map (e.g. an error message leaked the token).
        AgentExecutionDetail detail = AgentExecutionDetail.builder()
                .executionId(EXEC_ID)
                .agentName("test-agent")
                .status("COMPLETED")
                .output(Map.of("result", "gh CLI failed: authentication error for token " + SECRET_VALUE + " expired"))
                .build();
        when(agentService.getExecutionDetail(eq(EXEC_ID))).thenReturn(detail);

        mvc.perform(get("/api/agent/executions/" + EXEC_ID))
                .andExpect(status().isOk())
                // Plaintext secret must not appear anywhere in the response.
                .andExpect(content().string(Matchers.not(Matchers.containsString(SECRET_VALUE))))
                // The masker should have replaced it with the named-placeholder token.
                .andExpect(content().string(Matchers.containsString("***" + SECRET_NAME + "***")));
    }

    @Test
    void getExecutionDetail_noDisclosure_passesValueThrough() throws Exception {
        // A different execution id that has no disclosure record — even if the
        // body contains a string matching our stored secret, the advice should
        // not redact it because nothing was disclosed for THIS execution.
        String otherExec = "exec-no-disclosure-002";
        AgentExecutionDetail detail = AgentExecutionDetail.builder()
                .executionId(otherExec)
                .agentName("test-agent")
                .status("COMPLETED")
                .output(Map.of("result", "incidentally contains " + SECRET_VALUE))
                .build();
        when(agentService.getExecutionDetail(eq(otherExec))).thenReturn(detail);

        mvc.perform(get("/api/agent/executions/" + otherExec))
                .andExpect(status().isOk())
                .andExpect(content().string(Matchers.containsString(SECRET_VALUE)));
    }

    // ── Bug #5: status endpoint must also be masked ─────────────────────

    @Test
    void getStatus_redactsSecretValueInOutput() throws Exception {
        // GET /api/agent/{executionId}/status — bare-id route, no "executions" prefix.
        // The regex in SecretMaskingResponseAdvice originally required an
        // "execution(s)?" path segment and therefore skipped this URL entirely,
        // letting any leaked secret in the status payload through to the client.
        when(agentService.getStatus(eq(EXEC_ID)))
                .thenReturn(Map.of(
                        "executionId",
                        EXEC_ID,
                        "status",
                        "FAILED",
                        "reasonForIncompletion",
                        "tool error: HTTP 401 from upstream while using token " + SECRET_VALUE));

        mvc.perform(get("/api/agent/" + EXEC_ID + "/status"))
                .andExpect(status().isOk())
                .andExpect(content().string(Matchers.not(Matchers.containsString(SECRET_VALUE))))
                .andExpect(content().string(Matchers.containsString("***" + SECRET_NAME + "***")));
    }

    @Test
    void getSecret_endpointBodyNotMasked() throws Exception {
        // Sanity: /api/secrets/{key} returns plaintext (Conductor parity).
        // The advice must not activate here even though disclosures exist for this user.
        mvc.perform(get("/api/secrets/" + SECRET_NAME))
                .andExpect(status().isOk())
                .andExpect(content().string(SECRET_VALUE));
    }
}
