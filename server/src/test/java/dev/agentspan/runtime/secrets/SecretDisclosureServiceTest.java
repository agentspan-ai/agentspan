/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.secrets;

import static org.assertj.core.api.Assertions.*;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;

@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class SecretDisclosureServiceTest {

    @Autowired
    private SecretDisclosureService service;

    @Autowired
    @Qualifier("secretJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String USER = "disclosure-user-001";
    private static final String EXEC = "exec-disclosure-001";

    @BeforeEach
    void clean() {
        jdbc.update("DELETE FROM secret_disclosures WHERE user_id = :u", Map.of("u", USER));
    }

    @Test
    void record_thenLookup_returnsNames() {
        service.record(EXEC, USER, List.of("GITHUB_TOKEN", "OPENAI_API_KEY"));

        List<String> names = service.namesFor(EXEC, USER);

        assertThat(names).containsExactlyInAnyOrder("GITHUB_TOKEN", "OPENAI_API_KEY");
    }

    @Test
    void record_isIdempotent_doubleInsertDoesNotDuplicate() {
        service.record(EXEC, USER, List.of("GITHUB_TOKEN"));
        service.record(EXEC, USER, List.of("GITHUB_TOKEN"));

        assertThat(service.namesFor(EXEC, USER)).containsExactly("GITHUB_TOKEN");
    }

    @Test
    void namesFor_unknownExecution_returnsEmpty() {
        assertThat(service.namesFor("never-existed-exec", USER)).isEmpty();
    }

    @Test
    void record_emptyOrNullList_isNoOp() {
        service.record(EXEC, USER, List.of());
        service.record(EXEC, USER, null);
        assertThat(service.namesFor(EXEC, USER)).isEmpty();
    }

    @Test
    void namesFor_wrongUser_returnsEmpty() {
        // Defensive: even if attacker knew exec_id, queries filter by user_id
        service.record(EXEC, USER, List.of("GITHUB_TOKEN"));
        assertThat(service.namesFor(EXEC, "different-user")).isEmpty();
    }

    // ── Bug #1: secret_disclosures must be prunable to avoid unbounded growth ──

    @Test
    void pruneOlderThan_deletesOldRowsAndKeepsRecent() {
        // Seed an "old" disclosure (disclosed_at = 60 days ago) and a "recent" one
        // (disclosed_at = now). Pre-fix: service has no pruning, so both rows
        // remain forever — secret_disclosures grows unboundedly. The new
        // pruneOlderThan() must delete the old row and keep the recent one.
        String oldExec = "exec-OLD-" + System.nanoTime();
        String newExec = "exec-NEW-" + System.nanoTime();
        Instant longAgo = Instant.now().minus(60, ChronoUnit.DAYS);
        Instant recent = Instant.now();

        jdbc.update(
                "INSERT INTO secret_disclosures (execution_id, user_id, name, disclosed_at) "
                        + "VALUES (:e, :u, :n, :t)",
                Map.of("e", oldExec, "u", USER, "n", "OLD_TOKEN", "t", longAgo.toString()));
        jdbc.update(
                "INSERT INTO secret_disclosures (execution_id, user_id, name, disclosed_at) "
                        + "VALUES (:e, :u, :n, :t)",
                Map.of("e", newExec, "u", USER, "n", "NEW_TOKEN", "t", recent.toString()));

        int deleted = service.pruneOlderThan(30);

        assertThat(deleted).isEqualTo(1);
        assertThat(service.namesFor(oldExec, USER)).isEmpty();
        assertThat(service.namesFor(newExec, USER)).containsExactly("NEW_TOKEN");
    }

    @Test
    void pruneOlderThan_zeroDays_deletesEverything() {
        // Edge case: retention=0 means "delete anything older than now" — useful
        // for tests / ops who want to drain the table.
        service.record(EXEC, USER, List.of("TOKEN_A", "TOKEN_B"));
        assertThat(service.namesFor(EXEC, USER)).hasSize(2);

        int deleted = service.pruneOlderThan(0);

        assertThat(deleted).isGreaterThanOrEqualTo(2);
        assertThat(service.namesFor(EXEC, USER)).isEmpty();
    }
}
