package dev.agentspan.runtime.tasks;

import static com.netflix.conductor.common.metadata.tasks.TaskType.TASK_TYPE_JOIN;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.stereotype.Component;

import com.netflix.conductor.annotations.VisibleForTesting;
import com.netflix.conductor.common.metadata.workflow.WorkflowTask;
import com.netflix.conductor.common.utils.TaskUtils;
import com.netflix.conductor.core.config.ConductorProperties;
import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.core.execution.tasks.WorkflowSystemTask;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;

import lombok.extern.slf4j.Slf4j;

@Component(TASK_TYPE_JOIN)
@Slf4j
public class Join extends WorkflowSystemTask {

    /** Keys propagated from fork branch outputs into the JOIN output.
     *  Only these fields are copied — full tool results are omitted to keep
     *  the JOIN payload small.  Downstream consumers:
     *  <ul>
     *    <li>{@code _state_updates} — read by {@code stateMergeScript()} in ToolCompiler</li>
     *    <li>{@code state} — read by dynamic agent merge in AgentCompiler</li>
     *  </ul>
     */
    private static final Set<String> PROPAGATED_KEYS = Set.of("_state_updates", "state");

    @VisibleForTesting
    static final double EVALUATION_OFFSET_BASE = 1.2;

    private final ConductorProperties properties;

    public Join(ConductorProperties properties) {
        super(TASK_TYPE_JOIN);
        this.properties = properties;
        log.info("Using agentspan JOIN");
    }

    @Override
    @SuppressWarnings("unchecked")
    public boolean execute(WorkflowModel workflow, TaskModel task, WorkflowExecutor workflowExecutor) {
        StringBuilder failureReason = new StringBuilder();
        StringBuilder optionalTaskFailures = new StringBuilder();
        List<String> joinOn = (List<String>) task.getInputData().get("joinOn");
        if (task.isLoopOverTask()) {
            // If join is part of loop over task, wait for specific iteration to get complete
            joinOn = joinOn.stream()
                    .map(name -> TaskUtils.appendIteration(name, task.getIteration()))
                    .toList();
        }

        boolean allTasksTerminal = joinOn.stream()
                .map(workflow::getTaskByRefName)
                .allMatch(t -> t != null && t.getStatus().isTerminal());

        for (String joinOnRef : joinOn) {
            TaskModel forkedTask = workflow.getTaskByRefName(joinOnRef);
            if (forkedTask == null) {
                // Continue checking other tasks if a referenced task is not yet scheduled
                continue;
            }

            TaskModel.Status taskStatus = forkedTask.getStatus();

            // Determine if the join task fails immediately due to a non-optional, non-permissive
            // task failure,
            // or waits for all tasks to be terminal if the failed task is permissive.
            var isJoinFailure = !taskStatus.isSuccessful()
                    && !forkedTask.getWorkflowTask().isOptional()
                    && (!forkedTask.getWorkflowTask().isPermissive() || allTasksTerminal);
            if (isJoinFailure) {
                final String failureReasons = joinOn.stream()
                        .map(workflow::getTaskByRefName)
                        .filter(Objects::nonNull)
                        .filter(t -> !t.getStatus().isSuccessful())
                        .map(TaskModel::getReasonForIncompletion)
                        .collect(Collectors.joining(" "));
                failureReason.append(failureReasons);
                task.setReasonForIncompletion(failureReason.toString());
                task.setStatus(TaskModel.Status.FAILED);
                return true;
            }

            // check for optional task failures
            if (forkedTask.getWorkflowTask().isOptional() && taskStatus == TaskModel.Status.COMPLETED_WITH_ERRORS) {
                optionalTaskFailures
                        .append(String.format("%s/%s", forkedTask.getTaskDefName(), forkedTask.getTaskId()))
                        .append(" ");
            }
        }

        // Finalize the join task's status based on the outcomes of all referenced tasks.
        if (allTasksTerminal) {
            // Populate compact output: only copy fields needed by downstream consumers
            // (stateMergeScript reads _state_updates, dynamic agent merge reads state).
            // Full fork outputs are NOT copied — the LLM message builder reads them
            // directly from individual tool tasks, so duplicating here is pure waste.
            for (String joinOnRef : joinOn) {
                TaskModel forkedTask = workflow.getTaskByRefName(joinOnRef);
                if (forkedTask == null) continue;
                Map<String, Object> out = forkedTask.getOutputData();
                if (out == null || out.isEmpty()) continue;
                Map<String, Object> compact = new LinkedHashMap<>();
                for (String key : PROPAGATED_KEYS) {
                    if (out.containsKey(key)) {
                        compact.put(key, out.get(key));
                    }
                }
                if (!compact.isEmpty()) {
                    task.addOutput(joinOnRef, compact);
                }
            }

            if (!optionalTaskFailures.isEmpty()) {
                task.setStatus(TaskModel.Status.COMPLETED_WITH_ERRORS);
                optionalTaskFailures.append("completed with errors");
                task.setReasonForIncompletion(optionalTaskFailures.toString());
            } else {
                task.setStatus(TaskModel.Status.COMPLETED);
            }
            return true;
        }

        // Task execution not complete, waiting on more tasks to reach terminal state.
        return false;
    }

    @Override
    public Optional<Long> getEvaluationOffset(TaskModel taskModel, long maxOffset) {
        // Check if joinMode is set to SYNC — read directly from the workflow task definition
        // rather than from input data so the value is never duplicated into the task's payload.
        WorkflowTask workflowTask = taskModel.getWorkflowTask();
        if (workflowTask != null && WorkflowTask.JoinMode.SYNC == workflowTask.getJoinMode()) {
            // Synchronous mode: evaluate immediately every time (no backoff)
            return Optional.of(0L);
        }

        // Asynchronous mode (default): use exponential backoff
        int pollCount = taskModel.getPollCount();
        // Assuming pollInterval = 50ms and evaluationOffsetThreshold = 200 this will cause
        // a JOIN task to be evaluated continuously during the first 10 seconds and the FORK/JOIN
        // will end with minimal delay.
        if (pollCount <= properties.getSystemTaskPostponeThreshold()) {
            return Optional.of(0L);
        }

        double exp = pollCount - properties.getSystemTaskPostponeThreshold();
        return Optional.of(Math.min((long) Math.pow(EVALUATION_OFFSET_BASE, exp), maxOffset));
    }

    public boolean isAsync() {
        return true;
    }
}
