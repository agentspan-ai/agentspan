/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.util.ReflectionTestUtils;

import dev.agentspan.runtime.AgentRuntime;
import dev.agentspan.runtime.credentials.CredentialStoreProvider;
import dev.agentspan.runtime.credentials.ExecutionTokenService;
import dev.agentspan.runtime.model.credentials.ResolveRequest;

/**
 * Audit gaps C + F — full-stack {@code POST /api/workers/secrets} integration.
 *
 * <p>{@code WorkerSecretsTest} uses Mockito to stub the resolution service —
 * good for controller wiring but blind to the user-scoping behavior of the
 * real store. This test wires the real Spring beans (real
 * {@code CredentialResolutionService}, real {@code EncryptedDbCredentialStoreProvider},
 * real {@code ExecutionTokenService}) and exercises the integration boundary.</p>
 *
 * <p><strong>Gap C:</strong> two users, same secret name, different values.
 * Each user's execution token must return only its OWN value when the worker
 * calls {@code /api/workers/secrets}. Catches: cross-tenant leak via wrong
 * user_id binding in JDBC or wrong user_id extraction from the token.</p>
 *
 * <p><strong>Gap F:</strong> rotation semantics. A token doesn't snapshot — when
 * a secret is updated mid-execution, subsequent resolves return the new value.
 * Documents the design intent that workers see live values, not point-in-time
 * captures.</p>
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class WorkerCredentialsIntegrationTest {

    @Autowired
    private WorkerController controller;

    @Autowired
    private CredentialStoreProvider store;

    @Autowired
    private ExecutionTokenService tokenService;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    // Use a non-seeded name so the CredentialEnvSeeder doesn't accidentally
    // populate it for the anonymous user (and pollute the test).
    private static final String NAME = "_E2E_TENANT_TEST_KEY";

    private static final String USER_A = "tenant-test-user-A";
    private static final String USER_B = "tenant-test-user-B";

    @BeforeEach
    void setUp() {
        jdbc.update(
                "INSERT OR IGNORE INTO users (id, name, username, created_at) " + "VALUES (:i, :n, :u, :t)",
                Map.of(
                        "i",
                        USER_A,
                        "n",
                        "User A",
                        "u",
                        "tenantA",
                        "t",
                        Instant.now().toString()));
        jdbc.update(
                "INSERT OR IGNORE INTO users (id, name, username, created_at) " + "VALUES (:i, :n, :u, :t)",
                Map.of(
                        "i",
                        USER_B,
                        "n",
                        "User B",
                        "u",
                        "tenantB",
                        "t",
                        Instant.now().toString()));

        // Same name, different values
        store.set(USER_A, NAME, "VALUE-FROM-A");
        store.set(USER_B, NAME, "VALUE-FROM-B");

        // Tame the rate limit in case earlier tests in the same JVM
        // exhausted it.
        ReflectionTestUtils.setField(controller, "resolveRateLimit", 1000);
    }

    @AfterEach
    void cleanUp() {
        store.delete(USER_A, NAME);
        store.delete(USER_B, NAME);
        jdbc.update("DELETE FROM users WHERE id IN (:a, :b)", Map.of("a", USER_A, "b", USER_B));
    }

    // ── Gap C: cross-user isolation ─────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void resolve_eachUserGetsOnlyTheirOwnValue() {
        String tokenA = tokenService.mint(USER_A, "wf-A", List.of(NAME), 3600);
        String tokenB = tokenService.mint(USER_B, "wf-B", List.of(NAME), 3600);

        // User A's token
        ResolveRequest reqA = new ResolveRequest();
        reqA.setToken(tokenA);
        reqA.setNames(List.of(NAME));
        ResponseEntity<?> respA = controller.resolveCredentials(reqA);
        assertThat(respA.getStatusCode().value()).isEqualTo(200);
        Map<String, String> bodyA = (Map<String, String>) respA.getBody();
        assertThat(bodyA).containsEntry(NAME, "VALUE-FROM-A");
        // Critical: A's response must NOT contain B's value, anywhere.
        assertThat(bodyA.values()).doesNotContain("VALUE-FROM-B");

        // User B's token
        ResolveRequest reqB = new ResolveRequest();
        reqB.setToken(tokenB);
        reqB.setNames(List.of(NAME));
        ResponseEntity<?> respB = controller.resolveCredentials(reqB);
        assertThat(respB.getStatusCode().value()).isEqualTo(200);
        Map<String, String> bodyB = (Map<String, String>) respB.getBody();
        assertThat(bodyB).containsEntry(NAME, "VALUE-FROM-B");
        assertThat(bodyB.values()).doesNotContain("VALUE-FROM-A");
    }

    @Test
    @SuppressWarnings("unchecked")
    void resolve_userTokenCannotAccessOtherUserCredential_evenIfDeclared() {
        // User A's token declares a name that doesn't exist for user A.
        // (User B has it stored, but A's token must NOT reach B's storage.)
        store.delete(USER_A, NAME);
        String tokenA = tokenService.mint(USER_A, "wf-AX", List.of(NAME), 3600);

        ResolveRequest req = new ResolveRequest();
        req.setToken(tokenA);
        req.setNames(List.of(NAME));

        ResponseEntity<?> resp = controller.resolveCredentials(req);
        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        Map<String, String> body = (Map<String, String>) resp.getBody();
        // Server returns 200 with the missing name omitted (SDK turns this
        // into CredentialNotFoundError on the worker side). The crucial
        // property: B's value MUST NOT leak via A's token.
        assertThat(body).doesNotContainKey(NAME);
        assertThat(body.values()).doesNotContain("VALUE-FROM-B");
    }

    // ── Gap F: rotation semantics ───────────────────────────────────────

    @Test
    @SuppressWarnings("unchecked")
    void resolve_sameTokenSeesUpdatedValueAfterRotation() {
        String token = tokenService.mint(USER_A, "wf-rot", List.of(NAME), 3600);

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of(NAME));

        // First resolve → V1
        Map<String, String> first =
                (Map<String, String>) controller.resolveCredentials(req).getBody();
        assertThat(first).containsEntry(NAME, "VALUE-FROM-A");

        // Rotate to V2 while the SAME token is still valid
        store.set(USER_A, NAME, "ROTATED-VALUE-V2");

        // Second resolve with the same token → V2 (not snapshotted at mint)
        Map<String, String> second =
                (Map<String, String>) controller.resolveCredentials(req).getBody();
        assertThat(second).containsEntry(NAME, "ROTATED-VALUE-V2");

        // Final state matches the latest write
        assertThat(store.get(USER_A, NAME)).isEqualTo("ROTATED-VALUE-V2");
    }

    @Test
    void resolve_deletedCredentialDuringExecution_becomesUnresolvable() {
        // Edge case: credential is deleted between mint and resolve. The token is
        // still valid (it doesn't lock the value, only declared names), but
        // the response simply omits the unresolvable name.
        String token = tokenService.mint(USER_A, "wf-del", List.of(NAME), 3600);
        store.delete(USER_A, NAME);

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of(NAME));

        @SuppressWarnings("unchecked")
        Map<String, String> body =
                (Map<String, String>) controller.resolveCredentials(req).getBody();
        assertThat(body).doesNotContainKey(NAME);
    }

    // ── Bug #4: empty declared-names list MUST NOT permit arbitrary names ──

    @Test
    @SuppressWarnings("unchecked")
    void resolve_emptyDeclaredNames_rejectsAllRequestedNames() {
        // A token minted with an empty declared_names list (which happens for
        // every agent that doesn't declare credentials — the common case) must
        // NOT permit resolving arbitrary credential names. The defense-in-depth
        // claim of declared-name binding requires this.
        String token = tokenService.mint(USER_A, "wf-empty", List.of(), 3600);

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of(NAME));

        Map<String, String> body =
                (Map<String, String>) controller.resolveCredentials(req).getBody();
        // Pre-fix: this returned the actual stored value (bypass). After fix:
        // empty declared list means nothing is resolvable through this token.
        assertThat(body).isEmpty();
    }

    @Test
    @SuppressWarnings("unchecked")
    void resolve_emptyDeclaredNames_userBValueAlsoBlocked() {
        // Stronger: token has empty declared list, asks for User B's credential.
        // Even though A's user_id is authoritative (so cross-user leak wouldn't
        // happen anyway), the binding-check should reject the name itself
        // before any user-scoped resolve is attempted.
        String token = tokenService.mint(USER_A, "wf-empty2", List.of(), 3600);

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of(NAME));

        Map<String, String> body =
                (Map<String, String>) controller.resolveCredentials(req).getBody();
        assertThat(body.values()).doesNotContain("VALUE-FROM-B");
        assertThat(body.values()).doesNotContain("VALUE-FROM-A");
    }
}
