# Agent API UI Migration — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add missing agent API endpoints in `AgentController` that delegate to Conductor's `WorkflowService`/`ExecutionService`, then update all UI service files to call `/api/agent/` instead of `/workflow/`.

**Architecture:** Thin proxy endpoints in `AgentController` → `AgentService` → Conductor `WorkflowService`/`WorkflowExecutor`/`ExecutionService`. The UI switches from calling Conductor REST directly to calling our agent API. Response shapes are passed through unchanged (Conductor JSON).

**Tech Stack:** Java 21 / Spring Boot / Conductor 3.x, React / TypeScript

---

## File Structure

### Server (new endpoints delegate to Conductor)
- Modify: `server/src/main/java/dev/agentspan/runtime/controller/AgentController.java`
- Modify: `server/src/main/java/dev/agentspan/runtime/service/AgentService.java`

### UI (repoint API calls)
- Modify: `ui/src/commonServices/execution.ts`
- Modify: `ui/src/pages/execution/state/services.ts`
- Modify: `ui/src/pages/execution/TaskList/state/services.ts`
- Modify: `ui/src/pages/execution/RightPanel/state/services.ts`
- Modify: `ui/src/pages/executions/BulkActionModule.tsx`
- Modify: `ui/src/utils/query.ts`

### Tests
- Modify: `server/src/test/java/dev/agentspan/runtime/controller/` (new endpoint tests)

---

## Chunk 1: Server — Add Missing Agent API Endpoints

### Task 1: Add execution lifecycle endpoints to AgentService

**Files:**
- Modify: `server/src/main/java/dev/agentspan/runtime/service/AgentService.java`

These methods delegate directly to Conductor services already injected into AgentService.

- [ ] **Step 1: Add restart, retry, rerun, terminate, getExecution, getTasks, updateVariables methods**

Add these methods to `AgentService.java`:

```java
// ── Execution lifecycle (delegate to Conductor) ─────────────────

public void restartExecution(String executionId, boolean useLatestDefinitions) {
    workflowService.restartWorkflow(executionId, useLatestDefinitions);
}

public void retryExecution(String executionId, boolean resumeSubworkflowTasks) {
    workflowService.retryWorkflow(executionId, resumeSubworkflowTasks);
}

public String rerunExecution(String executionId, RerunWorkflowRequest request) {
    return workflowService.rerunWorkflow(executionId, request);
}

public void terminateExecution(String executionId, String reason) {
    workflowService.terminateWorkflow(executionId,
            reason != null ? reason : "Terminated by user");
}

public Workflow getFullExecution(String executionId) {
    return executionService.getExecutionStatus(executionId, true);
}

public List<Task> getExecutionTasks(String executionId, String status, int count, int start) {
    // Conductor's task listing is via the workflow object; filter from tasks list
    Workflow wf = executionService.getExecutionStatus(executionId, true);
    List<Task> tasks = wf.getTasks();
    if (status != null && !status.isEmpty()) {
        tasks = tasks.stream()
                .filter(t -> status.equals(t.getStatus().name()))
                .collect(Collectors.toList());
    }
    int end = Math.min(start + count, tasks.size());
    if (start >= tasks.size()) return List.of();
    return tasks.subList(start, end);
}

public void updateExecutionVariables(String executionId, Map<String, Object> variables) {
    Workflow wf = executionService.getExecutionStatus(executionId, false);
    wf.getVariables().putAll(variables);
    // Use workflowExecutor to persist
    workflowExecutor.getWorkflow(executionId, false);
    // Actually update via ExecutionDAO
    executionDAO.updateWorkflow(workflowExecutor.getWorkflow(executionId, false));
}

// ── Task operations ─────────────────────────────────────────────

public void updateTaskStatus(String executionId, String refTaskName,
                              String status, String workerId, Map<String, Object> body) {
    Workflow wf = executionService.getExecutionStatus(executionId, true);
    Task task = wf.getTasks().stream()
            .filter(t -> refTaskName.equals(t.getReferenceTaskName()))
            .reduce((first, second) -> second) // last occurrence
            .orElseThrow(() -> new NotFoundException("Task not found: " + refTaskName));

    TaskResult taskResult = new TaskResult(task);
    taskResult.setStatus(TaskResult.Status.valueOf(status));
    taskResult.setWorkerId(workerId);
    if (body != null) {
        taskResult.setOutputData(body);
    }
    executionService.updateTask(taskResult);
}

public List<Object> getTaskLogs(String taskId) {
    return executionService.getTaskLogs(taskId);
}

// ── Bulk operations ─────────────────────────────────────────────

public BulkResponse bulkPauseExecutions(List<String> executionIds) {
    return workflowBulkService.pauseWorkflow(executionIds);
}

public BulkResponse bulkResumeExecutions(List<String> executionIds) {
    return workflowBulkService.resumeWorkflow(executionIds);
}

public BulkResponse bulkRestartExecutions(List<String> executionIds, boolean useLatestDefs) {
    return workflowBulkService.restart(executionIds, useLatestDefs);
}

public BulkResponse bulkRetryExecutions(List<String> executionIds) {
    return workflowBulkService.retry(executionIds);
}

public BulkResponse bulkTerminateExecutions(List<String> executionIds, String reason) {
    return workflowBulkService.terminate(executionIds, reason);
}

// ── Metadata ────────────────────────────────────────────────────

public SearchResult<WorkflowSummary> searchExecutions(int start, int size, String sort,
                                                        String freeText, String query) {
    return workflowService.searchWorkflows(start, size, sort, freeText, query);
}

public WorkflowDef getExecutionDefinition(String name, Integer version) {
    if (version != null) {
        return metadataDAO.getWorkflowDef(name, version)
                .orElseThrow(() -> new NotFoundException("Definition not found: " + name));
    }
    return metadataDAO.getLatestWorkflowDef(name)
            .orElseThrow(() -> new NotFoundException("Definition not found: " + name));
}
```

**Note:** For `updateExecutionVariables`, the simplest approach is to use the `ExecutionDAOFacade` or work through the workflow model. Check if `executionDAO` is already available; if not, inject `ExecutionDAOFacade`. For `getTaskLogs`, check if `ExecutionService` exposes it — if not, use `ExecutionDAOFacade.getTaskExecutionLogs(taskId)`. For bulk operations, inject `WorkflowBulkService` from Conductor.

The exact implementation should be verified against the Conductor API available in the project. The key principle is: **delegate directly, don't reinvent**.

- [ ] **Step 2: Add required imports**

Ensure these are imported in `AgentService.java`:
```java
import com.netflix.conductor.common.metadata.workflow.RerunWorkflowRequest;
import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.common.run.Workflow;
import com.netflix.conductor.common.run.BulkResponse;
```

If `WorkflowBulkService` or `ExecutionDAOFacade` are needed, add them to the constructor.

- [ ] **Step 3: Verify compilation**

Run: `cd server && ./gradlew compileJava`
Expected: BUILD SUCCESSFUL

---

### Task 2: Add controller endpoints in AgentController

**Files:**
- Modify: `server/src/main/java/dev/agentspan/runtime/controller/AgentController.java`

- [ ] **Step 1: Add execution lifecycle endpoints**

```java
/** Get full execution with tasks (Conductor Workflow object). */
@GetMapping("/executions/{executionId}/full")
public Workflow getFullExecution(@PathVariable String executionId) {
    return agentService.getFullExecution(executionId);
}

/** Restart a completed/failed execution. */
@PostMapping("/executions/{executionId}/restart")
public void restartExecution(@PathVariable String executionId,
        @RequestParam(defaultValue = "false") boolean useLatestDefinitions) {
    agentService.restartExecution(executionId, useLatestDefinitions);
}

/** Retry a failed execution from the failed task. */
@PostMapping("/executions/{executionId}/retry")
public void retryExecution(@PathVariable String executionId,
        @RequestParam(defaultValue = "false") boolean resumeSubworkflowTasks) {
    agentService.retryExecution(executionId, resumeSubworkflowTasks);
}

/** Rerun execution from a specific task. */
@PostMapping("/executions/{executionId}/rerun")
public String rerunExecution(@PathVariable String executionId,
        @RequestBody RerunWorkflowRequest request) {
    return agentService.rerunExecution(executionId, request);
}

/** Terminate a running execution. */
@DeleteMapping("/executions/{executionId}")
public void terminateExecution(@PathVariable String executionId,
        @RequestParam(required = false) String reason) {
    agentService.terminateExecution(executionId, reason);
}

/** Get paginated task list for an execution. */
@GetMapping("/executions/{executionId}/tasks")
public List<Task> getExecutionTasks(@PathVariable String executionId,
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "15") int count,
        @RequestParam(defaultValue = "0") int start) {
    return agentService.getExecutionTasks(executionId, status, count, start);
}

/** Update execution variables. */
@PostMapping("/executions/{executionId}/variables")
public void updateExecutionVariables(@PathVariable String executionId,
        @RequestBody Map<String, Object> variables) {
    agentService.updateExecutionVariables(executionId, variables);
}

/** Update a task's status within an execution. */
@PostMapping("/tasks/{executionId}/{refTaskName}/{status}")
public void updateTaskStatus(@PathVariable String executionId,
        @PathVariable String refTaskName,
        @PathVariable String status,
        @RequestParam(defaultValue = "agent-ui") String workerid,
        @RequestBody(required = false) Map<String, Object> body) {
    agentService.updateTaskStatus(executionId, refTaskName, status, workerid, body);
}

/** Get task logs. */
@GetMapping("/tasks/{taskId}/log")
public Object getTaskLogs(@PathVariable String taskId) {
    return agentService.getTaskLogs(taskId);
}

// ── Search ──────────────────────────────────────────────────────

/** Search executions (pass-through to Conductor search). */
@GetMapping("/executions/search")
public SearchResult<WorkflowSummary> searchExecutionsRaw(
        @RequestParam(defaultValue = "0") int start,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(defaultValue = "startTime:DESC") String sort,
        @RequestParam(required = false) String freeText,
        @RequestParam(required = false) String query) {
    return agentService.searchExecutions(start, size, sort, freeText, query);
}

// ── Bulk operations ─────────────────────────────────────────────

@PutMapping("/executions/bulk/pause")
public BulkResponse bulkPause(@RequestBody List<String> ids) {
    return agentService.bulkPauseExecutions(ids);
}

@PutMapping("/executions/bulk/resume")
public BulkResponse bulkResume(@RequestBody List<String> ids) {
    return agentService.bulkResumeExecutions(ids);
}

@PostMapping("/executions/bulk/restart")
public BulkResponse bulkRestart(@RequestBody List<String> ids,
        @RequestParam(defaultValue = "false") boolean useLatestDefinitions) {
    return agentService.bulkRestartExecutions(ids, useLatestDefinitions);
}

@PostMapping("/executions/bulk/retry")
public BulkResponse bulkRetry(@RequestBody List<String> ids) {
    return agentService.bulkRetryExecutions(ids);
}

@PostMapping("/executions/bulk/terminate")
public BulkResponse bulkTerminate(@RequestBody List<String> ids,
        @RequestParam(required = false) String reason) {
    return agentService.bulkTerminateExecutions(ids, reason);
}

// ── Definition metadata ─────────────────────────────────────────

@GetMapping("/definitions/{name}")
public WorkflowDef getExecutionDefinition(@PathVariable String name,
        @RequestParam(required = false) Integer version) {
    return agentService.getExecutionDefinition(name, version);
}

@GetMapping("/definitions")
public List<WorkflowDef> listDefinitions() {
    return metadataDAO.getAllWorkflowDefs().stream()
            .map(def -> metadataDAO.getLatestWorkflowDef(def.getName()).orElse(null))
            .filter(Objects::nonNull)
            .collect(Collectors.toList());
}
```

- [ ] **Step 2: Add required imports to AgentController**

```java
import com.netflix.conductor.common.metadata.workflow.RerunWorkflowRequest;
import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.common.run.BulkResponse;
import com.netflix.conductor.common.run.SearchResult;
import com.netflix.conductor.common.run.Workflow;
import com.netflix.conductor.common.run.WorkflowSummary;
import com.netflix.conductor.dao.MetadataDAO;
import java.util.Objects;
```

Add `MetadataDAO` field and inject it (add to constructor):
```java
private final MetadataDAO metadataDAO;
```

- [ ] **Step 3: Build and test**

Run: `cd server && ./gradlew test`
Expected: BUILD SUCCESSFUL, all tests pass

- [ ] **Step 4: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/controller/AgentController.java \
        server/src/main/java/dev/agentspan/runtime/service/AgentService.java
git commit -m "feat: add agent API endpoints for execution lifecycle, tasks, bulk ops, and search"
```

---

## Chunk 2: UI — Repoint All API Calls

### Task 3: Update execution detail service

**Files:**
- Modify: `ui/src/commonServices/execution.ts`

- [ ] **Step 1: Change fetch URL from `/workflow/` to `/api/agent/executions/`**

```typescript
// Before:
const url = `/workflow/${executionId}?summarize=true`;
const introspectionUrl = `/workflow/introspection/records?workflowId=${executionId}`;

// After:
const url = `/api/agent/executions/${executionId}/full`;
const introspectionUrl = `/api/agent/executions/${executionId}/introspection`;
```

Note: If introspection isn't supported yet in the agent API, remove it or keep calling the old endpoint conditionally. The simplest approach: only change the main execution fetch for now, handle introspection in a follow-up.

---

### Task 4: Update execution action services

**Files:**
- Modify: `ui/src/pages/execution/state/services.ts`

- [ ] **Step 1: Repoint all `/workflow/` calls to `/api/agent/executions/`**

| Before | After |
|--------|-------|
| `/workflow/${id}/restart` | `/api/agent/executions/${id}/restart` |
| `/workflow/${id}/retry` | `/api/agent/executions/${id}/retry` |
| `DELETE /workflow/${id}` | `DELETE /api/agent/executions/${id}` |
| `/workflow/${id}/resume` | `/api/agent/${id}/resume` (already exists) |
| `/workflow/${id}/pause` | `/api/agent/${id}/pause` (already exists) |
| `/workflow/${id}/variables` | `/api/agent/executions/${id}/variables` |

---

### Task 5: Update task list service

**Files:**
- Modify: `ui/src/pages/execution/TaskList/state/services.ts`

- [ ] **Step 1: Change task list URL**

```typescript
// Before:
const executionTasksPath = `/workflow/${executionId}/tasks${queryString}`;

// After:
const executionTasksPath = `/api/agent/executions/${executionId}/tasks${queryString}`;
```

---

### Task 6: Update right panel services (task ops)

**Files:**
- Modify: `ui/src/pages/execution/RightPanel/state/services.ts`

- [ ] **Step 1: Update task status, logs, and rerun URLs**

```typescript
// Task status update:
// Before: `/tasks/${executionId}/${referenceTaskName}/${status}?workerid=conductor-ui`
// After:  `/api/agent/tasks/${executionId}/${referenceTaskName}/${status}?workerid=agent-ui`

// Task logs:
// Before: `/tasks/${selectedTask?.taskId}/log`
// After:  `/api/agent/tasks/${selectedTask?.taskId}/log`

// Rerun:
// Before: `/workflow/${executionId}/rerun`
// After:  `/api/agent/executions/${executionId}/rerun`
```

---

### Task 7: Update bulk operations

**Files:**
- Modify: `ui/src/pages/executions/BulkActionModule.tsx`

- [ ] **Step 1: Update all bulk endpoint URLs**

| Before | After |
|--------|-------|
| `/workflow/bulk/pause` | `/api/agent/executions/bulk/pause` |
| `/workflow/bulk/resume` | `/api/agent/executions/bulk/resume` |
| `/workflow/bulk/restart` | `/api/agent/executions/bulk/restart` |
| `/workflow/bulk/retry` | `/api/agent/executions/bulk/retry` |
| `/workflow/bulk/terminate` | `/api/agent/executions/bulk/terminate` |

---

### Task 8: Update search/query utilities

**Files:**
- Modify: `ui/src/utils/query.ts`

- [ ] **Step 1: Update search URLs**

```typescript
// Before:
"/workflow/search?"

// After:
"/api/agent/executions/search?"

// Deprecated search-by-tasks:
// Before: "/workflow/search-by-tasks?"
// After:  Remove or keep as legacy
```

---

### Task 9: Update any remaining `/workflow/` references in UI

**Files:** Various UI files that may reference `/workflow/` in fetch calls.

- [ ] **Step 1: Search for remaining `/workflow/` fetch URLs**

```bash
grep -rn '"/workflow/' ui/src/ --include='*.ts' --include='*.tsx' | grep -v node_modules
```

Fix any remaining occurrences following the same pattern.

- [ ] **Step 2: Build UI**

Run: `cd ui && pnpm build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Commit**

```bash
git add ui/
git commit -m "feat: migrate UI from Conductor /workflow/ API to /api/agent/ endpoints"
```

---

## Chunk 3: Integration Test

### Task 10: End-to-end verification

- [ ] **Step 1: Build and start server**

```bash
cd server && ./gradlew bootJar
java -jar build/libs/agentspan-runtime.jar &
```

- [ ] **Step 2: Test new endpoints via curl**

```bash
# Start an execution
curl -s http://localhost:6767/api/agent/start \
  -H "Content-Type: application/json" \
  -d '{"agentConfig":{"name":"test","model":"openai/gpt-4o","instructions":"Say hi"},"prompt":"hello"}' \
  | python3 -m json.tool

# Get full execution (new endpoint)
curl -s "http://localhost:6767/api/agent/executions/{id}/full" | python3 -m json.tool

# Get task list (new endpoint)
curl -s "http://localhost:6767/api/agent/executions/{id}/tasks" | python3 -m json.tool

# Search (new endpoint)
curl -s "http://localhost:6767/api/agent/executions/search?start=0&size=5" | python3 -m json.tool
```

- [ ] **Step 3: Run server tests**

```bash
cd server && ./gradlew test
```

- [ ] **Step 4: Build UI and verify**

```bash
cd ui && pnpm build
```

- [ ] **Step 5: Commit**

```bash
git commit -m "test: verify agent API endpoint migration"
```
