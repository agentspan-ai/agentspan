# Server-Side Dynamic DAG Task Injection

**Date:** 2026-03-20
**Status:** Approved

---

## Problem Statement

The SDK's `_AgentDagClient` calls two endpoints that don't exist on the Agentspan server:

- `POST /api/agent/{executionId}/tasks` — inject a display task into a running execution
- `POST /api/agent/workflow` — create a bare tracking workflow for sub-agent display

Without these, the Dynamic DAG feature is a no-op: hooks fire, HTTP calls fail silently, and the Conductor DAG shows only the single top-level `_fw_claude_*` task.

---

## Architecture

Two new endpoints in `AgentController` backed by a new `AgentDagService`. `AgentDagService` injects `ExecutionDAO` directly to mutate live execution and task state, bypassing the `WorkflowExecutor` decide loop.

**Why `ExecutionDAO` directly?** `ExecutionService.updateTask()` triggers `decide()` which tries to advance the execution according to its `WorkflowDef`. Injected tasks have no counterpart in the `WorkflowDef` — they are display-only. Using `ExecutionDAO` directly skips `decide()` and just persists the task to storage. `ExecutionDAO` is a Spring bean provided by Conductor's persistence module (`conductor-sqlite-persistence` / `conductor-postgres-persistence`).

**Why not `ExecutionDAOFacade`?** `ExecutionDAOFacade` adds external payload storage logic. Our task `inputData` is always small (tool arguments) — no need for that layer.

---

## Component 1: `AgentDagService`

New Spring `@Service` in `dev.agentspan.runtime.service`.

```java
@Service
@RequiredArgsConstructor
public class AgentDagService {
    private final ExecutionDAO executionDAO;
}
```

### Method: `injectTask`

```java
public InjectTaskResponse injectTask(String executionId, InjectTaskRequest req)
```

1. Load `WorkflowModel workflow = executionDAO.getWorkflow(executionId, true)`
   - Throw `ResponseStatusException(404)` if null
2. Build `TaskModel`:
   - `taskId = UUID.randomUUID().toString()`
   - `taskDefName = req.getTaskDefName()`
   - `referenceTaskName = req.getReferenceTaskName()`
   - `taskType = req.getType()` (`"SIMPLE"` or `"SUB_WORKFLOW"`)
   - `status = TaskModel.Status.IN_PROGRESS`
   - `workflowInstanceId = executionId`
   - `workflowType = workflow.getWorkflowName()`
   - `inputData = req.getInputData()`
   - `seq = workflow.getTasks().size() + 1`
   - `scheduledTime = startTime = System.currentTimeMillis()`
   - If `req.getSubWorkflowParam() != null`: set `subWorkflowId = req.getSubWorkflowParam().getExecutionId()`
3. `executionDAO.createTasks(List.of(task))`
4. Return `InjectTaskResponse(taskId)`

The task is linked to the execution via `workflowInstanceId`. `executionService.getExecutionStatus(executionId, true)` loads tasks from the `task` table indexed by `workflowInstanceId` — the injected task appears in the response without needing to update the in-memory `WorkflowModel`.

**Concurrency note:** `seq` is derived from `workflow.getTasks().size() + 1` at the time of the call. Under concurrent hook invocations, two calls could assign the same `seq`. This is safe — Conductor's SQLite/Postgres task storage does not enforce `seq` uniqueness as a constraint. Duplicate `seq` values on display-only tasks are cosmetically harmless.

When the SDK later calls native `POST /api/task` to complete/fail the task: Conductor marks the task COMPLETED/FAILED and runs `decide()`. Since the main Claude worker task (`_fw_claude_*`) is still `IN_PROGRESS`, the execution stays `RUNNING` — no disruption to the agent.

### Method: `createTrackingWorkflow`

```java
public CreateTrackingWorkflowResponse createTrackingWorkflow(CreateTrackingWorkflowRequest req)
```

1. Build a minimal `WorkflowDef`:
   - `name = req.getAgentName()`
   - `version = 1`
   - `tasks = emptyList()`
   - `inputParameters = List.of("prompt")`
2. Build `WorkflowModel`:
   - `workflowId = UUID.randomUUID().toString()`
   - `workflowDefinition = minimal def`
   - `status = WorkflowModel.Status.RUNNING`
   - `input = req.getInput()`
   - `createTime = System.currentTimeMillis()`
   - `workflowName = req.getAgentName()`  (via `workflow.getWorkflowName()` getter)
3. `executionDAO.createWorkflow(workflow)` — errors propagate as HTTP 500 via Spring's default error handling; no custom `ResponseStatusException` needed
4. Return `CreateTrackingWorkflowResponse(executionId)`

**Known limitation:** Tracking executions stay `RUNNING` permanently — they are never auto-completed. They appear in the execution list with their injected tasks visible. Completing tracking executions is deferred to a future enhancement.

---

## Component 2: New Endpoints in `AgentController`

```java
@PostMapping("/{executionId}/tasks")
public InjectTaskResponse injectTask(
        @PathVariable String executionId,
        @RequestBody InjectTaskRequest req) {
    return agentDagService.injectTask(executionId, req);
}

// Note: Spring MVC resolves static segments before dynamic ones,
// so POST /api/agent/workflow does not conflict with GET /api/agent/{name}.
@PostMapping("/workflow")
public CreateTrackingWorkflowResponse createTrackingWorkflow(
        @RequestBody CreateTrackingWorkflowRequest req) {
    return agentDagService.createTrackingWorkflow(req);
}
```

`AgentController` gains `AgentDagService` as a new injected dependency.

---

## Component 3: Request/Response Models

### `InjectTaskRequest`

```java
@Data
public class InjectTaskRequest {
    private String taskDefName;
    private String referenceTaskName;
    private String type;                     // "SIMPLE" or "SUB_WORKFLOW"
    private Map<String, Object> inputData;
    private String status;                   // expected: "IN_PROGRESS" (informational only)
    private SubWorkflowParam subWorkflowParam; // null for SIMPLE tasks

    @Data
    public static class SubWorkflowParam {
        private String name;
        private Integer version;
        private String executionId;           // pre-created tracking execution ID
    }
}
```

### `InjectTaskResponse`

```java
@Data
@AllArgsConstructor
public class InjectTaskResponse {
    private String taskId;
}
```

### `CreateTrackingWorkflowRequest`

```java
@Data
public class CreateTrackingWorkflowRequest {
    private String agentName;
    private Map<String, Object> input;
}
```

### `CreateTrackingWorkflowResponse`

```java
@Data
@AllArgsConstructor
public class CreateTrackingWorkflowResponse {
    private String executionId;
}
```

---

## File Map

| Action | Path |
|---|---|
| Create | `server/src/main/java/dev/agentspan/runtime/service/AgentDagService.java` |
| Create | `server/src/main/java/dev/agentspan/runtime/model/InjectTaskRequest.java` |
| Create | `server/src/main/java/dev/agentspan/runtime/model/InjectTaskResponse.java` |
| Create | `server/src/main/java/dev/agentspan/runtime/model/CreateTrackingWorkflowRequest.java` |
| Create | `server/src/main/java/dev/agentspan/runtime/model/CreateTrackingWorkflowResponse.java` |
| Modify | `server/src/main/java/dev/agentspan/runtime/controller/AgentController.java` |

---

## Testing Strategy

### Unit tests (`AgentDagServiceTest`)

- `injectTask` — mock `executionDAO`, verify `createTasks()` called with correct `TaskModel` fields
- `injectTask` with `SUB_WORKFLOW` type — verify `subWorkflowId` set on `TaskModel`
- `injectTask` unknown execution — verify 404 thrown
- `createTrackingWorkflow` — verify `createWorkflow()` called with `RUNNING` status and correct name/input

### Smoke test

Run the hello world example, fetch `GET /api/agent/execution/{executionId}`, assert `tasks.length > 1` (at least one injected tool task alongside the main worker task).

---

## What Is NOT Covered

- Completing tracking executions (stays `RUNNING` permanently)
- Task definition registration (injected tasks use task def names like `"Bash"`, `"Read"` — these may not be registered in Conductor's `MetadataDAO`, but that's fine for display-only tasks)
- Permission/HUMAN task injection (PermissionRequest hook not yet in SDK 0.1.26)
