# Deploy · Serve · Run · Plan

`AgentRuntime` exposes four distinct lifecycle operations. They split cleanly into two concerns:
**registering** workflow definitions on the server (control plane) and **running** the local tool
workers (data plane).

| Operation | Registers workflow def? | Starts an execution? | Runs local workers? | Blocks? |
|---|---|---|---|---|
| `plan(agent)` | no (compile only) | no | no | no |
| `deploy(agent…)` | yes | no | no | no |
| `serve(agent…)` | no | no | yes (until killed) | yes |
| `run(agent, prompt)` | yes (on start) | yes | yes | yes |

## plan — compile only

Compile an agent into a Conductor workflow definition without registering or starting anything.
Useful for inspecting the workflow shape or CI validation.

```java
CompileResponse compile = runtime.plan(agent);
Map<String,Object> workflowDef = compile.getWorkflowDef();
List<String> requiredWorkers  = compile.getRequiredWorkers();
```

## deploy — register, don't run

A CI/CD operation: push workflow + task definitions to the server. It does **not** register local
workers or start anything. Idempotent — safe to call on every startup.

```java
List<DeploymentInfo> infos = runtime.deploy(agentA, agentB);

// Deploy + reconcile cron schedules in one call (see Scheduling):
runtime.deploy(agent, List.of(
    Schedule.builder().name("daily").cron("0 9 * * *").build()));
```

## serve — run the workers

The runtime side of `deploy`: register the agent's tool workers and poll for tasks indefinitely.
Use this in a long-running worker process for agents whose executions are started elsewhere
(scheduled runs, the UI, another service). A JVM shutdown hook stops workers on SIGTERM.

```java
runtime.serve(agentA, agentB);   // blocks until the process is killed
```

A typical production split: one process calls `deploy(...)` at release time; one or more worker
processes call `serve(...)`; executions are triggered by schedules or API.

## run — register, start, and wait

The all-in-one path for interactive use: register workers, start the execution, and block for the
result. `start(...)` is the same thing without the wait — it returns an `AgentHandle` immediately.

```java
AgentResult result = runtime.run(agent, "What is the capital of France?");

// Fire-and-forget, then poll/approve later:
AgentHandle handle = runtime.start(agent, prompt);
AgentResult later  = handle.waitForResult();
```

## resume — re-attach after a restart

Re-attach to an execution started in a previous process and re-register its workers — for crash
recovery or planned restarts.

```java
AgentHandle handle = runtime.resume(executionId, agent);
AgentResult result = handle.waitForResult();
```

Every operation has an `…Async` variant returning a `CompletableFuture` (`runAsync`, `startAsync`,
`streamAsync`, `deployAsync`, `resumeAsync`). See the [AgentRuntime API reference](../agent-runtime-api.md).
