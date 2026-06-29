/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.eval;

import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.*;

import lombok.RequiredArgsConstructor;

@Component
@RestController
@RequestMapping("/api/eval")
@RequiredArgsConstructor
public class EvalController {

    private final EvalService evalService;

    // ── Eval Runs ──────────────────────────────────────────────────────

    /** Submit an eval suite result from the SDK. */
    @PostMapping("/runs")
    public EvalRunDto submitEvalRun(@RequestBody EvalRunDto dto) {
        return evalService.saveEvalRun(dto);
    }

    /** List eval runs (paginated), newest first. */
    @GetMapping("/runs")
    public Map<String, Object> listEvalRuns(
            @RequestParam(defaultValue = "0") int start, @RequestParam(defaultValue = "20") int size) {
        return evalService.listEvalRuns(start, size);
    }

    /** Get a single eval run with all case and check details. */
    @GetMapping("/runs/{id}")
    public ResponseEntity<?> getEvalRun(@PathVariable String id) {
        try {
            return ResponseEntity.ok(evalService.getEvalRun(id));
        } catch (NoSuchElementException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
        }
    }

    // ── Datasets ───────────────────────────────────────────────────────

    /** Push (upsert) a named dataset from the SDK. */
    @PostMapping("/datasets")
    public ResponseEntity<Void> pushDataset(@RequestBody DatasetDto dto) {
        evalService.pushDataset(dto);
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    /** List all datasets (summary — name, updatedAt, pushedBy, caseCount). */
    @GetMapping("/datasets")
    public List<DatasetDto> listDatasets() {
        return evalService.listDatasets();
    }

    /** Get a single dataset with all cases. */
    @GetMapping("/datasets/{name}")
    public ResponseEntity<?> getDataset(@PathVariable String name) {
        try {
            return ResponseEntity.ok(evalService.getDataset(name));
        } catch (NoSuchElementException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
        }
    }
}
