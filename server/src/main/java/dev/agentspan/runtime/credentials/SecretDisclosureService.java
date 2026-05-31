/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/**
 * Records which secret names were resolved for each execution.
 *
 * <p>{@link dev.agentspan.runtime.controller.WorkerController} writes a row to
 * {@code secret_disclosures} every time a worker successfully resolves a name
 * via {@code POST /api/workers/secrets}. {@link SecretOutputMasker} reads
 * these rows on the execution-read path to know which secret values to redact
 * from response payloads.</p>
 *
 * <p>Idempotent — duplicate inserts (same execution_id + name) are ignored.</p>
 */
@Service
public class SecretDisclosureService {

    private static final Logger log = LoggerFactory.getLogger(SecretDisclosureService.class);

    private final NamedParameterJdbcTemplate jdbc;
    private final int retentionDays;

    public SecretDisclosureService(
            @Qualifier("secretJdbc") NamedParameterJdbcTemplate jdbc,
            @Value("${agentspan.secrets.disclosure-retention-days:30}") int retentionDays) {
        this.jdbc = jdbc;
        this.retentionDays = retentionDays;
    }

    /** Record that {@code names} were disclosed to a worker running {@code executionId} for {@code userId}. */
    public void record(String executionId, String userId, List<String> names) {
        if (names == null || names.isEmpty()) return;
        String now = Instant.now().toString();
        for (String name : names) {
            jdbc.update(
                    "INSERT INTO secret_disclosures (execution_id, user_id, name, disclosed_at) "
                            + "VALUES (:e, :u, :n, :t) ON CONFLICT DO NOTHING",
                    Map.of("e", executionId, "u", userId, "n", name, "t", now));
        }
    }

    /** Return all secret names disclosed for {@code executionId} owned by {@code userId}. */
    public List<String> namesFor(String executionId, String userId) {
        List<String> result = new ArrayList<>();
        jdbc.query(
                "SELECT name FROM secret_disclosures WHERE execution_id = :e AND user_id = :u",
                Map.of("e", executionId, "u", userId),
                (ResultSetExtractor<Void>) rs -> {
                    while (rs.next()) result.add(rs.getString("name"));
                    return null;
                });
        return result;
    }

    /**
     * Delete disclosure rows older than {@code days} ago. Returns rows deleted.
     * Used by the scheduled pruner; also callable directly for ops/tests.
     */
    public int pruneOlderThan(int days) {
        String cutoff = Instant.now().minus(days, ChronoUnit.DAYS).toString();
        return jdbc.update("DELETE FROM secret_disclosures WHERE disclosed_at < :cutoff", Map.of("cutoff", cutoff));
    }

    /**
     * Hourly background prune. Disclosure rows are an unbounded log otherwise:
     * every worker-side secret resolution writes one. Retention default is
     * 30 days, configurable via {@code agentspan.secrets.disclosure-retention-days}.
     */
    @Scheduled(fixedDelay = 3_600_000L, initialDelay = 60_000L)
    public void pruneScheduled() {
        try {
            int n = pruneOlderThan(retentionDays);
            if (n > 0) {
                log.info("Pruned {} secret_disclosures row(s) older than {} day(s)", n, retentionDays);
            }
        } catch (Exception e) {
            log.warn("secret_disclosures prune failed: {}", e.toString());
        }
    }
}
