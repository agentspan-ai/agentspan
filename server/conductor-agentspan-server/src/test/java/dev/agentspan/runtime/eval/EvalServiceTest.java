package dev.agentspan.runtime.eval;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

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
class EvalServiceTest {

    @Autowired
    private EvalService evalService;

    @Autowired
    @Qualifier("evalJdbc")
    private NamedParameterJdbcTemplate jdbc;

    // Unique prefix per test class execution — prevents accidentally deleting unrelated rows
    // in a shared database if the test profile is misconfigured.
    private static final String P =
            "evaltest-" + java.util.UUID.randomUUID().toString().substring(0, 8) + "-";

    @BeforeEach
    void cleanup() {
        jdbc.update(
                "DELETE FROM eval_checks WHERE eval_case_id IN (SELECT id FROM eval_cases WHERE eval_run_id LIKE :prefix)",
                Map.of("prefix", P + "%"));
        jdbc.update("DELETE FROM eval_cases WHERE eval_run_id LIKE :prefix", Map.of("prefix", P + "%"));
        jdbc.update("DELETE FROM eval_runs WHERE id LIKE :prefix", Map.of("prefix", P + "%"));
        jdbc.update("DELETE FROM eval_datasets WHERE name LIKE :prefix", Map.of("prefix", P + "%"));
    }

    private String id(String suffix) {
        return P + suffix;
    }

    // ── Eval Runs ───────────────────────────────────────────────────

    @Test
    void saveEvalRun_persistsAndCanBeRetrieved() {
        EvalRunDto dto = EvalRunDto.builder()
                .id(id("run-1"))
                .agentName("billing-agent")
                .timestamp("2025-01-01T00:00:00Z")
                .totalCases(2)
                .passedCases(1)
                .build();

        EvalRunDto saved = evalService.saveEvalRun(dto);

        assertThat(saved.getId()).isEqualTo(id("run-1"));
        assertThat(saved.getAgentName()).isEqualTo("billing-agent");
        assertThat(saved.getTotalCases()).isEqualTo(2);
        assertThat(saved.getPassedCases()).isEqualTo(1);
    }

    @Test
    void getEvalRun_returnsNotFound_forMissingId() {
        assertThatThrownBy(() -> evalService.getEvalRun("does-not-exist"))
                .isInstanceOf(NoSuchElementException.class)
                .hasMessageContaining("does-not-exist");
    }

    @Test
    void saveEvalRun_withCasesAndChecks_roundTrips() {
        EvalCheckDto check1 =
                EvalCheckDto.builder().check("status").passed(true).message("").build();
        EvalCheckDto check2 = EvalCheckDto.builder()
                .check("output_contains:'refund'")
                .passed(false)
                .message("Output did not contain 'refund'")
                .build();
        EvalCheckDto semanticCheck = EvalCheckDto.builder()
                .check("assert_output_satisfies")
                .passed(true)
                .score(0.87)
                .reasoning("Response accurately addressed the issue")
                .build();

        EvalCaseDto caseDto = EvalCaseDto.builder()
                .name("billing_routes_correctly")
                .passed(false)
                .agentName("billing-agent")
                .checks(List.of(check1, check2, semanticCheck))
                .build();

        EvalRunDto dto = EvalRunDto.builder()
                .id(id("run-2"))
                .agentName("billing-agent")
                .timestamp("2025-01-01T00:00:00Z")
                .totalCases(1)
                .passedCases(0)
                .cases(List.of(caseDto))
                .build();

        evalService.saveEvalRun(dto);

        EvalRunDto retrieved = evalService.getEvalRun(id("run-2"));

        assertThat(retrieved.getCases()).hasSize(1);
        EvalCaseDto retrievedCase = retrieved.getCases().get(0);
        assertThat(retrievedCase.getName()).isEqualTo("billing_routes_correctly");
        assertThat(retrievedCase.isPassed()).isFalse();
        assertThat(retrievedCase.getChecks()).hasSize(3);

        EvalCheckDto retrievedSemantic = retrievedCase.getChecks().stream()
                .filter(c -> c.getScore() != null)
                .findFirst()
                .orElseThrow();
        assertThat(retrievedSemantic.getScore()).isCloseTo(0.87, org.assertj.core.data.Offset.offset(0.01));
        assertThat(retrievedSemantic.getReasoning()).isEqualTo("Response accurately addressed the issue");
    }

    @Test
    void listEvalRuns_returnsAll_inDescendingTimestampOrder() {
        evalService.saveEvalRun(EvalRunDto.builder()
                .id(id("run-a"))
                .agentName("agent-a")
                .timestamp("2025-01-01T00:00:00Z")
                .totalCases(1)
                .passedCases(1)
                .build());
        evalService.saveEvalRun(EvalRunDto.builder()
                .id(id("run-b"))
                .agentName("agent-b")
                .timestamp("2025-02-01T00:00:00Z")
                .totalCases(2)
                .passedCases(0)
                .build());

        Map<String, Object> result = evalService.listEvalRuns(0, 50);

        @SuppressWarnings("unchecked")
        List<EvalRunDto> runs = (List<EvalRunDto>) result.get("results");
        List<String> ids = runs.stream().map(EvalRunDto::getId).toList();

        assertThat(ids).contains(id("run-a"), id("run-b"));
        // Newer timestamp should come first
        int idxB = ids.indexOf(id("run-b"));
        int idxA = ids.indexOf(id("run-a"));
        assertThat(idxB).isLessThan(idxA);
    }

    // ── Datasets ────────────────────────────────────────────────────

    @Test
    void pushDataset_persistsAndCanBeRetrieved() {
        DatasetDto.DatasetCaseDto c1 = DatasetDto.DatasetCaseDto.builder()
                .name("billing_case")
                .prompt("I need a refund")
                .assertions(List.of("handoff_to:billing"))
                .build();

        DatasetDto dto =
                DatasetDto.builder().name(id("dataset-1")).cases(List.of(c1)).build();

        evalService.pushDataset(dto);

        DatasetDto retrieved = evalService.getDataset(id("dataset-1"));

        assertThat(retrieved.getName()).isEqualTo(id("dataset-1"));
        assertThat(retrieved.getCases()).hasSize(1);
        assertThat(retrieved.getCases().get(0).getPrompt()).isEqualTo("I need a refund");
        assertThat(retrieved.getCases().get(0).getAssertions()).contains("handoff_to:billing");
    }

    @Test
    void pushDataset_storesCaseCount() {
        DatasetDto dto = DatasetDto.builder()
                .name(id("dataset-count"))
                .cases(List.of(
                        DatasetDto.DatasetCaseDto.builder()
                                .name("c1")
                                .prompt("p1")
                                .build(),
                        DatasetDto.DatasetCaseDto.builder()
                                .name("c2")
                                .prompt("p2")
                                .build(),
                        DatasetDto.DatasetCaseDto.builder()
                                .name("c3")
                                .prompt("p3")
                                .build()))
                .build();

        evalService.pushDataset(dto);

        List<DatasetDto> list = evalService.listDatasets();
        DatasetDto summary = list.stream()
                .filter(d -> d.getName().equals(id("dataset-count")))
                .findFirst()
                .orElseThrow();

        assertThat(summary.getCaseCount()).isEqualTo(3);
        // List response must NOT include full cases
        assertThat(summary.getCases()).isNull();
    }

    @Test
    void pushDataset_upserts_onSecondPush() {
        DatasetDto first = DatasetDto.builder()
                .name(id("dataset-upsert"))
                .cases(List.of(DatasetDto.DatasetCaseDto.builder()
                        .name("c1")
                        .prompt("p1")
                        .build()))
                .build();
        DatasetDto second = DatasetDto.builder()
                .name(id("dataset-upsert"))
                .cases(List.of(
                        DatasetDto.DatasetCaseDto.builder()
                                .name("c1")
                                .prompt("p1")
                                .build(),
                        DatasetDto.DatasetCaseDto.builder()
                                .name("c2")
                                .prompt("p2")
                                .build()))
                .build();

        evalService.pushDataset(first);
        evalService.pushDataset(second);

        DatasetDto retrieved = evalService.getDataset(id("dataset-upsert"));
        assertThat(retrieved.getCases()).hasSize(2);
        assertThat(retrieved.getCaseCount()).isEqualTo(2);
    }

    @Test
    void getDataset_throwsNotFound_forMissingName() {
        assertThatThrownBy(() -> evalService.getDataset("no-such-dataset")).isInstanceOf(NoSuchElementException.class);
    }
}
