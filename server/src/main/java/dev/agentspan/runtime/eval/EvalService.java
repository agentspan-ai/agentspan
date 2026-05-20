/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.eval;

import java.time.Instant;
import java.util.*;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import dev.agentspan.runtime.auth.RequestContextHolder;

@Service
public class EvalService {

    private static final Logger log = LoggerFactory.getLogger(EvalService.class);
    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() {};
    private static final TypeReference<List<DatasetDto.DatasetCaseDto>> CASE_LIST = new TypeReference<>() {};

    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public EvalService(@Qualifier("evalJdbc") NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    // ── Eval Runs ──────────────────────────────────────────────────────

    @Transactional
    public EvalRunDto saveEvalRun(EvalRunDto dto) {
        String runId = dto.getId() != null ? dto.getId() : UUID.randomUUID().toString();
        String timestamp =
                dto.getTimestamp() != null ? dto.getTimestamp() : Instant.now().toString();
        String createdBy =
                RequestContextHolder.get().map(ctx -> ctx.getUser().getEmail()).orElse(null);

        // agent_name is nullable — multi-agent evals may not have a single canonical agent
        String agentName = dto.getAgentName() != null ? dto.getAgentName() : "";

        String tagsJson = toJson(dto.getTags());

        jdbc.update(
                "INSERT OR REPLACE INTO eval_runs"
                        + " (id, agent_name, timestamp, total_cases, passed_cases, tags, created_by, name, strategy, ran_by)"
                        + " VALUES (:id, :agentName, :timestamp, :totalCases, :passedCases, :tags, :createdBy, :name, :strategy, :ranBy)",
                new MapSqlParameterSource()
                        .addValue("id", runId)
                        .addValue("agentName", agentName)
                        .addValue("timestamp", timestamp)
                        .addValue("totalCases", dto.getTotalCases())
                        .addValue("passedCases", dto.getPassedCases())
                        .addValue("tags", tagsJson)
                        .addValue("createdBy", createdBy)
                        .addValue("name", dto.getName())
                        .addValue("strategy", dto.getStrategy())
                        .addValue("ranBy", dto.getRanBy()));

        if (dto.getCases() != null) {
            for (EvalCaseDto caseDto : dto.getCases()) {
                saveCaseWithChecks(runId, caseDto);
            }
        }

        log.debug("Saved eval run {} ({}/{} passed)", runId, dto.getPassedCases(), dto.getTotalCases());
        return dto.toBuilder()
                .id(runId)
                .timestamp(timestamp)
                .createdBy(createdBy)
                .build();
    }

    private void saveCaseWithChecks(String runId, EvalCaseDto caseDto) {
        String caseId =
                caseDto.getId() != null ? caseDto.getId() : UUID.randomUUID().toString();

        jdbc.update(
                "INSERT OR REPLACE INTO eval_cases"
                        + " (id, eval_run_id, case_name, passed, error, agent_name, model, tags, prompt, output)"
                        + " VALUES (:id, :evalRunId, :caseName, :passed, :error, :agentName, :model, :tags, :prompt, :output)",
                new MapSqlParameterSource()
                        .addValue("id", caseId)
                        .addValue("evalRunId", runId)
                        .addValue("caseName", caseDto.getName())
                        .addValue("passed", caseDto.isPassed() ? 1 : 0)
                        .addValue("error", caseDto.getError())
                        .addValue("agentName", caseDto.getAgentName())
                        .addValue("model", caseDto.getModel())
                        .addValue("tags", toJson(caseDto.getTags()))
                        .addValue("prompt", caseDto.getPrompt())
                        .addValue("output", caseDto.getOutput()));

        if (caseDto.getChecks() != null) {
            for (EvalCheckDto check : caseDto.getChecks()) {
                saveCheck(caseId, check);
            }
        }
    }

    private void saveCheck(String caseId, EvalCheckDto check) {
        String checkId =
                check.getId() != null ? check.getId() : UUID.randomUUID().toString();
        jdbc.update(
                "INSERT OR REPLACE INTO eval_checks (id, eval_case_id, check_name, passed, message, score, reasoning)"
                        + " VALUES (:id, :evalCaseId, :checkName, :passed, :message, :score, :reasoning)",
                new MapSqlParameterSource()
                        .addValue("id", checkId)
                        .addValue("evalCaseId", caseId)
                        .addValue("checkName", check.getCheck())
                        .addValue("passed", check.isPassed() ? 1 : 0)
                        .addValue("message", check.getMessage())
                        .addValue("score", check.getScore())
                        .addValue("reasoning", check.getReasoning()));
    }

    public Map<String, Object> listEvalRuns(int start, int size) {
        long total = Optional.ofNullable(
                        jdbc.queryForObject("SELECT COUNT(*) FROM eval_runs", new MapSqlParameterSource(), Long.class))
                .orElse(0L);

        List<EvalRunDto> results = jdbc.query(
                "SELECT id, agent_name, timestamp, total_cases, passed_cases, tags, created_by, name, strategy, ran_by"
                        + " FROM eval_runs ORDER BY timestamp DESC LIMIT :size OFFSET :start",
                new MapSqlParameterSource().addValue("size", size).addValue("start", start),
                (rs, rowNum) -> EvalRunDto.builder()
                        .id(rs.getString("id"))
                        .agentName(rs.getString("agent_name"))
                        .timestamp(rs.getString("timestamp"))
                        .totalCases(rs.getInt("total_cases"))
                        .passedCases(rs.getInt("passed_cases"))
                        .tags(fromJson(rs.getString("tags")))
                        .createdBy(rs.getString("created_by"))
                        .name(rs.getString("name"))
                        .strategy(rs.getString("strategy"))
                        .ranBy(rs.getString("ran_by"))
                        .build());

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("totalHits", total);
        response.put("results", results);
        return response;
    }

    public EvalRunDto getEvalRun(String id) {
        List<EvalRunDto> runs = jdbc.query(
                "SELECT id, agent_name, timestamp, total_cases, passed_cases, tags, created_by, name, strategy, ran_by"
                        + " FROM eval_runs WHERE id = :id",
                new MapSqlParameterSource("id", id),
                (rs, rowNum) -> EvalRunDto.builder()
                        .id(rs.getString("id"))
                        .agentName(rs.getString("agent_name"))
                        .timestamp(rs.getString("timestamp"))
                        .totalCases(rs.getInt("total_cases"))
                        .passedCases(rs.getInt("passed_cases"))
                        .tags(fromJson(rs.getString("tags")))
                        .createdBy(rs.getString("created_by"))
                        .name(rs.getString("name"))
                        .strategy(rs.getString("strategy"))
                        .ranBy(rs.getString("ran_by"))
                        .build());

        if (runs.isEmpty()) {
            throw new NoSuchElementException("Eval run not found: " + id);
        }

        EvalRunDto run = runs.get(0);
        List<EvalCaseDto> cases = loadCasesForRun(id);
        return run.toBuilder().cases(cases).build();
    }

    private List<EvalCaseDto> loadCasesForRun(String runId) {
        // Load cases first so the result set (and its connection) is fully consumed
        // before we issue the nested checks query. With a single-connection SQLite pool
        // calling loadChecksForCase() inside the RowMapper would deadlock.
        List<EvalCaseDto> cases = jdbc.query(
                "SELECT id, case_name, passed, error, agent_name, model, tags, prompt, output"
                        + " FROM eval_cases WHERE eval_run_id = :runId",
                new MapSqlParameterSource("runId", runId),
                (rs, rowNum) -> EvalCaseDto.builder()
                        .id(rs.getString("id"))
                        .evalRunId(runId)
                        .name(rs.getString("case_name"))
                        .passed(rs.getInt("passed") == 1)
                        .error(rs.getString("error"))
                        .agentName(rs.getString("agent_name"))
                        .model(rs.getString("model"))
                        .tags(fromJson(rs.getString("tags")))
                        .prompt(rs.getString("prompt"))
                        .output(rs.getString("output"))
                        .build());

        // Now enrich each case with its checks (connection is free between each call)
        return cases.stream()
                .map(c -> c.toBuilder().checks(loadChecksForCase(c.getId())).build())
                .toList();
    }

    private List<EvalCheckDto> loadChecksForCase(String caseId) {
        return jdbc.query(
                "SELECT id, check_name, passed, message, score, reasoning FROM eval_checks WHERE eval_case_id = :caseId",
                new MapSqlParameterSource("caseId", caseId),
                (rs, rowNum) -> {
                    double scoreVal = rs.getDouble("score");
                    Double score = rs.wasNull() ? null : scoreVal;
                    return EvalCheckDto.builder()
                            .id(rs.getString("id"))
                            .evalCaseId(caseId)
                            .check(rs.getString("check_name"))
                            .passed(rs.getInt("passed") == 1)
                            .message(rs.getString("message"))
                            .score(score)
                            .reasoning(rs.getString("reasoning"))
                            .build();
                });
    }

    // ── Datasets ───────────────────────────────────────────────────────

    public void pushDataset(DatasetDto dto) {
        String updatedAt = Instant.now().toString();
        String casesJson = toJson(dto.getCases());
        int caseCount = dto.getCases() != null ? dto.getCases().size() : 0;

        jdbc.update(
                "INSERT OR REPLACE INTO eval_datasets (name, cases_json, updated_at, pushed_by, case_count)"
                        + " VALUES (:name, :casesJson, :updatedAt, :pushedBy, :caseCount)",
                new MapSqlParameterSource()
                        .addValue("name", dto.getName())
                        .addValue("casesJson", casesJson)
                        .addValue("updatedAt", updatedAt)
                        .addValue("pushedBy", dto.getPushedBy())
                        .addValue("caseCount", caseCount));

        log.debug("Pushed dataset '{}' ({} cases)", dto.getName(), caseCount);
    }

    /** List all datasets — metadata only, does NOT load or parse cases JSON. */
    public List<DatasetDto> listDatasets() {
        return jdbc.query(
                "SELECT name, updated_at, pushed_by, case_count FROM eval_datasets ORDER BY name",
                new MapSqlParameterSource(),
                (rs, rowNum) -> DatasetDto.builder()
                        .name(rs.getString("name"))
                        .updatedAt(rs.getString("updated_at"))
                        .pushedBy(rs.getString("pushed_by"))
                        .caseCount(rs.getInt("case_count"))
                        .build());
    }

    public DatasetDto getDataset(String name) {
        List<DatasetDto> results = jdbc.query(
                "SELECT name, cases_json, updated_at, pushed_by, case_count FROM eval_datasets WHERE name = :name",
                new MapSqlParameterSource("name", name),
                (rs, rowNum) -> DatasetDto.builder()
                        .name(rs.getString("name"))
                        .updatedAt(rs.getString("updated_at"))
                        .pushedBy(rs.getString("pushed_by"))
                        .caseCount(rs.getInt("case_count"))
                        .cases(parseCases(rs.getString("cases_json")))
                        .build());

        if (results.isEmpty()) {
            throw new NoSuchElementException("Dataset not found: " + name);
        }
        return results.get(0);
    }

    // ── JSON helpers ───────────────────────────────────────────────────

    private String toJson(Object obj) {
        if (obj == null) return null;
        try {
            return mapper.writeValueAsString(obj);
        } catch (Exception e) {
            log.warn("Failed to serialize object to JSON: {}", e.getMessage());
            return null;
        }
    }

    private List<String> fromJson(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            return mapper.readValue(json, STRING_LIST);
        } catch (Exception e) {
            log.warn("Failed to deserialize JSON tags: {}", e.getMessage());
            return List.of();
        }
    }

    private List<DatasetDto.DatasetCaseDto> parseCases(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            return mapper.readValue(json, CASE_LIST);
        } catch (Exception e) {
            log.warn("Failed to deserialize dataset cases JSON: {}", e.getMessage());
            return List.of();
        }
    }
}
