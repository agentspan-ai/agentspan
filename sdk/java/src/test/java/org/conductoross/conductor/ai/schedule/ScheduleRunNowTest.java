// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.schedule;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

import org.junit.jupiter.api.Test;

import com.netflix.conductor.client.http.WorkflowClient;
import com.netflix.conductor.common.metadata.workflow.StartWorkflowRequest;
import com.netflix.conductor.common.run.Workflow;
import com.netflix.conductor.common.run.Workflow.WorkflowStatus;

/**
 * Pure unit tests for the name-keyed {@code runNow} overloads (Fix 4).
 *
 * <p>No network: the {@link WorkflowClient} is subclassed to stub
 * {@code startWorkflow} / {@code getWorkflow}, and {@link Schedules} is
 * subclassed to stub the {@code get(name)} lookup.
 */
class ScheduleRunNowTest {

    private static ScheduleInfo info(String agent) {
        return new ScheduleInfo(
                agent + "-daily", "daily", agent, "0 0 9 * * ?", "UTC",
                Map.of("k", "v"), false, null, false, null, null, null, null, null, null, null, null);
    }

    /** A WorkflowClient that records start requests and serves canned getWorkflow results. */
    private static final class FakeWorkflowClient extends WorkflowClient {
        String startedName;
        Map<String, Object> startedInput;
        Workflow[] statusSequence;
        int polls = 0;

        FakeWorkflowClient() {
            // Avoid touching any real ConductorClient/network.
            super(new com.netflix.conductor.client.http.ConductorClient("http://localhost:0"));
        }

        @Override
        public String startWorkflow(StartWorkflowRequest req) {
            this.startedName = req.getName();
            this.startedInput = req.getInput();
            return "wf-123";
        }

        @Override
        public Workflow getWorkflow(String workflowId, boolean includeTasks) {
            Workflow wf = statusSequence[Math.min(polls, statusSequence.length - 1)];
            polls++;
            return wf;
        }
    }

    private static Workflow wf(WorkflowStatus status) {
        Workflow w = new Workflow();
        w.setStatus(status);
        return w;
    }

    /** Schedules subclass that returns a canned ScheduleInfo for get(name). */
    private static Schedules schedulesWith(FakeWorkflowClient fwc, ScheduleInfo canned) {
        return new Schedules(new com.netflix.conductor.client.http.ConductorClient("http://localhost:0"), fwc) {
            @Override
            public ScheduleInfo get(String wireName) {
                return canned;
            }
        };
    }

    @Test
    void runNowByName_startsWorkflowWithStoredInput_returnsExecutionId() {
        FakeWorkflowClient fwc = new FakeWorkflowClient();
        Schedules schedules = schedulesWith(fwc, info("my_agent"));

        String executionId = schedules.runNow("my_agent-daily");

        assertEquals("wf-123", executionId);
        assertEquals("my_agent", fwc.startedName, "must start the schedule's agent workflow");
        assertEquals(Map.of("k", "v"), fwc.startedInput, "must use the schedule's stored input");
    }

    @Test
    void runNowByName_noWait_returnsExecutionId() {
        FakeWorkflowClient fwc = new FakeWorkflowClient();
        Schedules schedules = schedulesWith(fwc, info("my_agent"));

        Object result = schedules.runNow("my_agent-daily", false);
        assertEquals("wf-123", result);
        assertEquals(0, fwc.polls, "non-wait must not poll for status");
    }

    @Test
    void runNowAndWait_pollsToTerminalAndReturnsWorkflow() {
        FakeWorkflowClient fwc = new FakeWorkflowClient();
        Workflow running = wf(WorkflowStatus.RUNNING);
        Workflow done = wf(WorkflowStatus.COMPLETED);
        fwc.statusSequence = new Workflow[] {running, running, done};

        Schedules schedules = schedulesWith(fwc, info("my_agent"));

        // 0ms poll interval keeps the test fast/deterministic.
        Workflow result = schedules.runNowAndWait("my_agent-daily", 5_000L, 0L);

        assertSame(done, result, "must return the terminal workflow");
        assertEquals(3, fwc.polls, "must poll until terminal");
        assertTrue(result.getStatus().isTerminal());
    }

    @Test
    void runNowAndWait_timesOut() {
        FakeWorkflowClient fwc = new FakeWorkflowClient();
        fwc.statusSequence = new Workflow[] {wf(WorkflowStatus.RUNNING)};

        Schedules schedules = schedulesWith(fwc, info("my_agent"));

        assertThrows(
                ScheduleException.class,
                () -> schedules.runNowAndWait("my_agent-daily", 0L, 0L),
                "must raise once the deadline passes without a terminal state");
    }

    @Test
    void isTerminal_helper() {
        assertTrue(Schedules.isTerminal(wf(WorkflowStatus.COMPLETED)));
        assertTrue(Schedules.isTerminal(wf(WorkflowStatus.FAILED)));
        assertTrue(Schedules.isTerminal(wf(WorkflowStatus.TERMINATED)));
        assertTrue(Schedules.isTerminal(wf(WorkflowStatus.TIMED_OUT)));
        assertFalse(Schedules.isTerminal(wf(WorkflowStatus.RUNNING)));
        assertFalse(Schedules.isTerminal(wf(WorkflowStatus.PAUSED)));
    }
}
