/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import org.conductoross.conductor.AgentRuntime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Integration test for CredentialController — real server, real DB, no mocks.
 * Uses MockMvc for HTTP layer but all services are real Spring beans.
 */
@SpringBootTest(classes = AgentRuntime.class)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class CredentialControllerTest {

    @Autowired
    private MockMvc mvc;

    private static final String CRED_NAME = "_CONTROLLER_TEST_KEY";

    @BeforeEach
    void cleanUp() throws Exception {
        // Delete test credential if it exists
        mvc.perform(delete("/api/credentials/" + CRED_NAME));
    }

    @Test
    void createAndListCredential() throws Exception {
        // Create
        mvc.perform(post("/api/credentials")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"" + CRED_NAME + "\",\"value\":\"test-secret\"}"))
            .andExpect(status().isCreated());

        // List — should contain our credential
        mvc.perform(get("/api/credentials"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[?(@.name=='" + CRED_NAME + "')]").exists())
            .andExpect(jsonPath("$[?(@.name=='" + CRED_NAME + "')].partial").value("test...cret"));
    }

    @Test
    void deleteCredential_returns204() throws Exception {
        // Create first
        mvc.perform(post("/api/credentials")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"" + CRED_NAME + "\",\"value\":\"to-delete\"}"))
            .andExpect(status().isCreated());

        // Delete
        mvc.perform(delete("/api/credentials/" + CRED_NAME))
            .andExpect(status().isNoContent());

        // Verify gone — list should not contain it
        mvc.perform(get("/api/credentials"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[?(@.name=='" + CRED_NAME + "')]").doesNotExist());
    }

    @Test
    void updateCredential_changesValue() throws Exception {
        // Create
        mvc.perform(post("/api/credentials")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"" + CRED_NAME + "\",\"value\":\"original-value-here\"}"))
            .andExpect(status().isCreated());

        // Update
        mvc.perform(put("/api/credentials/" + CRED_NAME)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"value\":\"updated-value-here\"}"))
            .andExpect(status().isOk());

        // Verify partial changed
        mvc.perform(get("/api/credentials"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[?(@.name=='" + CRED_NAME + "')].partial").value("upda...here"));
    }

    @Test
    void resolve_withoutToken_returns401() throws Exception {
        mvc.perform(post("/api/credentials/resolve")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"names\":[\"GITHUB_TOKEN\"]}"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void resolve_withInvalidToken_returns401() throws Exception {
        mvc.perform(post("/api/credentials/resolve")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"token\":\"garbage-token\",\"names\":[\"GITHUB_TOKEN\"]}"))
            .andExpect(status().isUnauthorized());
    }
}
