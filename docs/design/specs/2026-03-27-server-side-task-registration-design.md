# Server-Side Task Definition Registration

**Date:** 2026-03-27
**Status:** Approved

## Overview

Move all Conductor task definition registration from SDKs to the server. When `POST /api/agent/start` compiles a workflow, the server registers all task defs. SDKs only poll for tasks.

## Problem

Task def registration (timeout, retry config) is duplicated in 3 places:
- Python SDK: `_default_task_def` / `_passthrough_task_def` in runtime.py
- TypeScript SDK: `registerTaskDef()` in worker.ts
- Java server: `AgentService.registerTaskDef()` in AgentService.java

Already caused bugs where 120s was hardcoded in all three independently.

## Design

### Server: Register all task defs during compilation

After `compile()` in `AgentService`, walk the entire workflow tree and register a task def for every SIMPLE task. The server already has `registerTaskDef()` — extend it to handle all tasks, not just system ones.

**Tool-specific timeouts:** Agent config serializes `timeoutSeconds` per tool. Server reads this during registration — if present, uses it for `responseTimeoutSeconds`.

**Default config:**
- `timeoutSeconds: 0` (no overall timeout)
- `responseTimeoutSeconds: 3600` (Conductor minimum is 1s)
- `retryCount: 2`
- `retryDelaySeconds: 2`
- `retryLogic: LINEAR_BACKOFF`

### Python SDK: Disable task def registration

Set `register_task_def=False` on all `worker_task()` calls. Remove `_default_task_def()` and `_passthrough_task_def()`.

### TypeScript SDK: Disable task def registration

Remove `registerTaskDef()` calls from `runtime.ts`. Make `registerTaskDef()` in `worker.ts` a no-op (keep for backward compat but don't call Conductor).

### Design doc update

Update `docs/sdk-design/2026-03-23-multi-language-sdk-design.md` Section 5.2 to reflect server-side registration as the standard.

## Files Changed

| File | Change |
|---|---|
| `server/.../service/AgentService.java` | Add `registerAllTaskDefs(WorkflowDef)` that walks workflow tree |
| `sdk/python/.../runtime/runtime.py` | Set `register_task_def=False` everywhere, remove task def factories |
| `sdk/typescript/src/runtime.ts` | Remove `registerTaskDef()` calls |
| `sdk/typescript/src/worker.ts` | Make `registerTaskDef()` a no-op |
| `docs/sdk-design/2026-03-23-multi-language-sdk-design.md` | Update Section 5.2 |
| Tests | Update/add tests for all changes |
