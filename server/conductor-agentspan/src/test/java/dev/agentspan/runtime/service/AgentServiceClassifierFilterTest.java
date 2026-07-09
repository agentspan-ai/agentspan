/*
 * Copyright (c) 2026 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/**
 * Unit tests for {@link AgentService#withClassifierFilter(String, String)} — the folding of the
 * optional classifier request parameter into Conductor's structured search query. Deterministic —
 * pure string logic.
 */
class AgentServiceClassifierFilterTest {

    @Test
    void nullOrBlankClassifierLeavesQueryUntouched() {
        assertThat(AgentService.withClassifierFilter("status = 'RUNNING'", null))
                .isEqualTo("status = 'RUNNING'");
        assertThat(AgentService.withClassifierFilter("status = 'RUNNING'", "  "))
                .isEqualTo("status = 'RUNNING'");
        assertThat(AgentService.withClassifierFilter(null, null)).isNull();
    }

    @Test
    void classifierOnlyBecomesTheQuery() {
        assertThat(AgentService.withClassifierFilter(null, "agent"))
                .isEqualTo("classifier IN (agent)");
        assertThat(AgentService.withClassifierFilter("", "agent"))
                .isEqualTo("classifier IN (agent)");
    }

    @Test
    void classifierIsAppendedToExistingQuery() {
        assertThat(AgentService.withClassifierFilter("status = 'RUNNING'", "agent"))
                .isEqualTo("status = 'RUNNING' AND classifier IN (agent)");
    }

    @Test
    void commaSeparatedValuesAreTrimmed() {
        assertThat(AgentService.withClassifierFilter(null, " agent , workflow "))
                .isEqualTo("classifier IN (agent,workflow)");
    }

    @Test
    void degenerateClassifierValueIsIgnored() {
        assertThat(AgentService.withClassifierFilter("status = 'RUNNING'", " , ,"))
                .isEqualTo("status = 'RUNNING'");
    }
}
