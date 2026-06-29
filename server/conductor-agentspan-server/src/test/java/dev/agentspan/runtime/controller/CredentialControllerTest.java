/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import dev.agentspan.runtime.AgentRuntime;

/**
 * Conductor-parity contract for /api/secrets.
 *
 * Mirrors io.orkes.conductor.server.rest.SecretResource:
 *   POST   /secrets              → List<String> of names
 *   GET    /secrets              → Set<String> of names (Conductor parity; same set as POST in OSS)
 *   GET    /secrets/{key}        → plaintext value (text/plain)
 *   PUT    /secrets/{key}        → upsert; raw-string body; max 65535 chars
 *   DELETE /secrets/{key}        → 200 OK (Conductor parity)
 *   GET    /secrets/{key}/exists → boolean
 *   GET    /secrets/v2           → CredentialMeta (name, partial, timestamps)
 *
 * Key-name validation (all {key} endpoints):
 *   - Non-blank
 *   - Pattern: [a-zA-Z0-9_-]+ (Conductor's ALLOWED_SECRET_NAME_PATTERN)
 *   - Max length: 65535
 */
@SpringBootTest(classes = AgentRuntime.class)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class CredentialControllerTest {

    @Autowired
    private MockMvc mvc;

    private static final String KEY = "_CREDENTIAL_CTRL_TEST_KEY";

    @BeforeEach
    void cleanUp() throws Exception {
        mvc.perform(delete("/api/secrets/" + KEY));
    }

    // ── CRUD ──────────────────────────────────────────────────────────

    @Test
    void putCredential_createsAndReturnsValueOnGet() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("plaintext-secret-value"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/secrets/" + KEY))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_PLAIN))
                .andExpect(content().string("plaintext-secret-value"));
    }

    @Test
    void putCredential_upserts_overwritingExistingValue() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v1"))
                .andExpect(status().isOk());
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v2"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/secrets/" + KEY))
                .andExpect(status().isOk())
                .andExpect(content().string("v2"));
    }

    @Test
    void getCredential_missing_returns404() throws Exception {
        mvc.perform(get("/api/secrets/" + KEY)).andExpect(status().isNotFound());
    }

    @Test
    void deleteCredential_returns200_andSecretIsGone() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("to-delete"))
                .andExpect(status().isOk());

        mvc.perform(delete("/api/secrets/" + KEY)).andExpect(status().isOk());

        mvc.perform(get("/api/secrets/" + KEY)).andExpect(status().isNotFound());
    }

    @Test
    void putCredential_emptyValue_returns400() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content(""))
                .andExpect(status().isBadRequest());
    }

    // ── Key-name validation (all {key} endpoints) ──────────────────────

    @Test
    void invalidKey_containsSlash_returns400() throws Exception {
        // Slashes are outside [a-zA-Z0-9_-]+ — path traversal guard
        mvc.perform(put("/api/secrets/bad%2Fkey")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("v"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/secrets/bad%2Fkey")).andExpect(status().isBadRequest());
        mvc.perform(delete("/api/secrets/bad%2Fkey")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/secrets/bad%2Fkey/exists")).andExpect(status().isBadRequest());
    }

    @Test
    void invalidKey_containsSpecialChars_returns400() throws Exception {
        mvc.perform(put("/api/secrets/bad%40key")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("v"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void validKey_allowsAlphanumericUnderscoreDash() throws Exception {
        String valid = "Valid_Key-123";
        try {
            mvc.perform(put("/api/secrets/" + valid)
                            .contentType(MediaType.TEXT_PLAIN)
                            .content("v"))
                    .andExpect(status().isOk());
        } finally {
            mvc.perform(delete("/api/secrets/" + valid));
        }
    }

    // ── List ──────────────────────────────────────────────────────────

    @Test
    void postListNames_returnsStringArray_containingCreatedSecret() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v"))
                .andExpect(status().isOk());

        mvc.perform(post("/api/secrets"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@=='" + KEY + "')]").exists());
    }

    @Test
    void getList_returnsSet_containingCreatedSecret() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/secrets"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@=='" + KEY + "')]").exists());
    }

    // ── Exists ────────────────────────────────────────────────────────

    @Test
    void exists_trueWhenPresent_falseWhenAbsent() throws Exception {
        mvc.perform(get("/api/secrets/" + KEY + "/exists"))
                .andExpect(status().isOk())
                .andExpect(content().string("false"));

        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/secrets/" + KEY + "/exists"))
                .andExpect(status().isOk())
                .andExpect(content().string("true"));
    }

    // ── /v2 (richer metadata) ──────────────────────────────────────────

    @Test
    void v2List_returnsCredentialMeta_withFullShape() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY)
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("plaintext-with-decent-length"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/secrets/v2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.name=='" + KEY + "')]").exists())
                .andExpect(jsonPath("$[?(@.name=='" + KEY + "')].partial").exists())
                .andExpect(jsonPath("$[?(@.name=='" + KEY + "')].created_at").exists())
                .andExpect(jsonPath("$[?(@.name=='" + KEY + "')].updated_at").exists())
                // Plaintext MUST NOT appear in v2 response
                .andExpect(content()
                        .string(org.hamcrest.Matchers.not(
                                org.hamcrest.Matchers.containsString("plaintext-with-decent-length"))));
    }
}
