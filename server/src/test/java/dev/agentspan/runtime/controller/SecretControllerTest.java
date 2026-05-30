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
 *   POST   /secrets                  → List<String> of names
 *   GET    /secrets                  → Set<String> of names (RBAC-filtered; same set in OSS)
 *   GET    /secrets/{key}            → plaintext value (text/plain)
 *   PUT    /secrets/{key}            → upsert; raw-string body
 *   DELETE /secrets/{key}            → 204
 *   GET    /secrets/{key}/exists     → boolean
 *   GET    /secrets/{key}/tags       → List<Tag>
 *   PUT    /secrets/{key}/tags       → add tags
 *   DELETE /secrets/{key}/tags       → remove tags
 */
@SpringBootTest(classes = AgentRuntime.class)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class SecretControllerTest {

    @Autowired
    private MockMvc mvc;

    private static final String KEY = "_SECRET_CTRL_TEST_KEY";

    @BeforeEach
    void cleanUp() throws Exception {
        mvc.perform(delete("/api/secrets/" + KEY));
    }

    // ── CRUD ──────────────────────────────────────────────────────────

    @Test
    void putSecret_createsAndReturnsValueOnGet() throws Exception {
        // PUT body is raw string (Conductor parity), not JSON object
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("plaintext-secret-value"))
                .andExpect(status().isOk());

        // GET returns plaintext as text/plain
        mvc.perform(get("/api/secrets/" + KEY))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_PLAIN))
                .andExpect(content().string("plaintext-secret-value"));
    }

    @Test
    void putSecret_upserts_overwritingExistingValue() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v1"))
                .andExpect(status().isOk());
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v2"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/secrets/" + KEY))
                .andExpect(status().isOk())
                .andExpect(content().string("v2"));
    }

    @Test
    void getSecret_missing_returns404() throws Exception {
        mvc.perform(get("/api/secrets/" + KEY)).andExpect(status().isNotFound());
    }

    @Test
    void deleteSecret_returns204_andSecretIsGone() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("to-delete"))
                .andExpect(status().isOk());

        mvc.perform(delete("/api/secrets/" + KEY)).andExpect(status().isNoContent());

        mvc.perform(get("/api/secrets/" + KEY)).andExpect(status().isNotFound());
    }

    // ── List ──────────────────────────────────────────────────────────

    @Test
    void postListNames_returnsStringArray_containingCreatedSecret() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v"))
                .andExpect(status().isOk());

        // POST /api/secrets (Conductor's primary listing endpoint) — returns List<String>
        mvc.perform(post("/api/secrets"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@=='" + KEY + "')]").exists());
    }

    @Test
    void getList_returnsStringSet_containingCreatedSecret() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v"))
                .andExpect(status().isOk());

        // GET /api/secrets — RBAC-filtered list (same set as POST in OSS, no RBAC)
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

    // ── Tags ──────────────────────────────────────────────────────────

    @Test
    void tags_putGetDelete_roundTrip() throws Exception {
        mvc.perform(put("/api/secrets/" + KEY).contentType(MediaType.TEXT_PLAIN).content("v"))
                .andExpect(status().isOk());

        // Empty initially
        mvc.perform(get("/api/secrets/" + KEY + "/tags"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));

        // PUT add two tags
        mvc.perform(put("/api/secrets/" + KEY + "/tags")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("[{\"key\":\"env\",\"value\":\"prod\"},{\"key\":\"team\",\"value\":\"core\"}]"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/secrets/" + KEY + "/tags"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.key=='env' && @.value=='prod')]").exists())
                .andExpect(jsonPath("$[?(@.key=='team' && @.value=='core')]").exists());

        // DELETE one tag
        mvc.perform(delete("/api/secrets/" + KEY + "/tags")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("[{\"key\":\"env\",\"value\":\"prod\"}]"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/secrets/" + KEY + "/tags"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.key=='env')]").doesNotExist())
                .andExpect(jsonPath("$[?(@.key=='team')]").exists());
    }

    // ── /v2 (richer metadata) ──────────────────────────────────────────

    @Test
    void v2List_returnsSecretMeta_withFullShape() throws Exception {
        // Audit gap G — assert the UI-facing v2 contract:
        // each element MUST have name + partial + created_at + updated_at,
        // and tags MUST be propagated when present.
        mvc.perform(put("/api/secrets/" + KEY)
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("plaintext-with-decent-length"))
                .andExpect(status().isOk());
        mvc.perform(put("/api/secrets/" + KEY + "/tags")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("[{\"key\":\"env\",\"value\":\"prod\"}]"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/secrets/v2"))
                .andExpect(status().isOk())
                // The created secret must be in the result with the full shape.
                .andExpect(jsonPath("$[?(@.name=='" + KEY + "')]").exists())
                .andExpect(jsonPath("$[?(@.name=='" + KEY + "')].partial").exists())
                .andExpect(jsonPath("$[?(@.name=='" + KEY + "')].created_at").exists())
                .andExpect(jsonPath("$[?(@.name=='" + KEY + "')].updated_at").exists())
                // Tags propagated under tags[].key/value
                .andExpect(jsonPath("$[?(@.name=='" + KEY + "')].tags[?(@.key=='env' && @.value=='prod')]")
                        .exists())
                // Plaintext MUST NOT appear in v2 (security boundary —
                // v2 returns metadata only, never the raw value).
                .andExpect(content()
                        .string(org.hamcrest.Matchers.not(
                                org.hamcrest.Matchers.containsString("plaintext-with-decent-length"))));
    }
}
