# Migrating from Agentspan to Orkes Conductor

Agentspan has merged into **[Orkes Conductor](https://github.com/conductor-oss/conductor)**.
The durable-agent runtime that powered Agentspan now ships inside the Conductor server, and the
agent SDK ships inside the official Conductor Python SDK. **Your agents keep running — for most
code this migration is an install line, an import path, and a server URL.**

Every code sample in this guide was executed against `conductor-python[agents]==2.0.0` (GA) and
a live Conductor `3.32.1` (GA) server before publishing.

---

## TL;DR

| | Agentspan (old) | Orkes Conductor (new) |
|---|---|---|
| Install | `pip install agentspan` | `pip install "conductor-python[agents]>=2.0.0"` |
| Imports | `from agentspan.agents import …` | `from conductor.ai.agents import …` |
| Connect | `configure(server_url=…)` | `AgentRuntime(Configuration(server_api_url=…))` |
| Server | `agentspan server start` → `:6767` | `docker run … conductoross/conductor` → API `:8080/api`, UI `:5000` |
| Run id | `workflow_id` | `execution_id` |
| Env vars | `AGENTSPAN_*` | `CONDUCTOR_*` |
| `@tool`, `Agent(…)`, `Strategy` | — | **unchanged** |
| Repo | `agentspan-ai/agentspan` (archived) | [`conductor-oss/conductor`](https://github.com/conductor-oss/conductor) |
| Docs | agentspan.ai/docs | [orkes.io/content/devguide/ai](https://orkes.io/content/devguide/ai) |

---

## 1. Install

```bash
pip install "conductor-python[agents]>=2.0.0"
```

The `agents` extra exists only on the 2.x line (2.0.0 went GA on 2026-08-03). It pulls the
framework adapters (`openai-agents`, `google-adk`, `langchain`/`langgraph`, `anthropic`, …);
narrower extras exist if you want less: `[openai]`, `[langgraph]`, `[adk]`, `[anthropic]`.

> **Coming from `conductor-agent-sdk` 0.3.x/0.4.x instead of `agentspan`?** That package was the
> interim name for this same SDK (it continues Agentspan's version numbering past 0.2.0) and
> already uses the `conductor.ai.agents` import paths — your imports need no change; switch the
> install line to `conductor-python[agents]>=2.0.0`, which is where development continues.

The old packages remain installable forever (`agentspan==0.2.1` is the final release; it only
adds a `DeprecationWarning`), but they receive no fixes and target the pre-merge server.

## 2. Run the server

Old:

```bash
agentspan server start          # API + UI on http://localhost:6767
```

New — the fused server is the standard Conductor image, with the agent runtime embedded:

```bash
docker run -d --name conductor \
  -p 8080:8080 -p 5000:5000 \
  -e OPENAI_API_KEY \
  conductoross/conductor:3.32.1   # or the latest tag: hub.docker.com/r/conductoross/conductor
```

Two ports now: **`8080`** serves the API (your SDK talks to `http://localhost:8080/api`) and
**`5000`** serves the UI (`http://localhost:5000`). Readiness probe:
`curl -sf http://localhost:8080/api/metadata/workflow`.

The old `agentspan/server` Docker image is frozen at `0.4.4` and stays pullable, but all new
work lands in `conductoross/conductor`. There is no fused equivalent of the `agentspan` CLI —
the server story is Docker (or [self-hosted deployment](https://orkes.io/content/devguide/running/deploy)).

## 3. Your first migrated agent

The `@tool` decorator, `Agent(...)` constructor, and every `Strategy` member are **unchanged**.
What changes: the import root, and the module-level singleton (`run()` / `configure()`) becomes
an explicit `AgentRuntime`.

**Before (agentspan):**

```python
from agentspan.agents import Agent, tool, run, configure

@tool
def check_balance(account_id: str) -> dict:
    """Check the balance of a bank account."""
    return {"account_id": account_id, "balance": 5432.10, "currency": "USD"}

billing = Agent(
    name="billing",
    model="openai/gpt-5.6-sol",
    instructions="Handle billing questions: balances, payments, invoices.",
    tools=[check_balance],
)

configure(server_url="http://localhost:6767")
result = run(billing, "What's the balance on account ACC-123?")
result.print_result()
```

**After (Conductor):**

```python
from conductor.ai.agents import Agent, AgentRuntime, tool
from conductor.client.configuration.configuration import Configuration

@tool
def check_balance(account_id: str) -> dict:
    """Check the balance of a bank account."""
    return {"account_id": account_id, "balance": 5432.10, "currency": "USD"}

billing = Agent(
    name="billing",
    model="openai/gpt-5.6-sol",
    instructions="Handle billing questions: balances, payments, invoices.",
    tools=[check_balance],
)

if __name__ == "__main__":
    with AgentRuntime(Configuration(server_api_url="http://localhost:8080/api")) as runtime:
        result = runtime.run(billing, "What's the balance on account ACC-123?")
        result.print_result()
```

Executed output (GA SDK, 3.32.1 GA server):

```
╒══════════════════════════════════════════════════╕
│ Agent Output                                     │
╘══════════════════════════════════════════════════╛

The balance on account **ACC-123** is **$5,432.10 USD**.

Tool calls: 1
Tokens: 287 total (242 prompt, 45 completion)
Finish reason: FinishReason.STOP
Execution ID: efd289d6-...
```

Three things to notice:

- **`AgentRuntime` is explicit.** `AgentRuntime(Configuration(server_api_url=...))` replaces
  `configure(...)` + module-level `run(...)`. A kwargs form also exists
  (`AgentRuntime(server_url=..., api_key=..., api_secret=...)`). The context manager replaces
  `shutdown()` — worker cleanup happens on exit.
- **Guard your entrypoint.** The worker pool spawns subprocesses that re-import your module;
  without `if __name__ == "__main__":` you get duplicate runs and tools stuck in `SCHEDULED`.
- **`workflow_id` is now `execution_id`.** Everywhere. `result.execution_id`,
  `handle.execution_id`, `runtime.get_status(execution_id)`. The UI always called it
  "Execution ID" — the API name now matches.

## 4. API mapping

| Agentspan | Conductor | Notes |
|---|---|---|
| `configure(server_url=…)` | `AgentRuntime(Configuration(server_api_url=…))` | or `AgentRuntime(server_url=…)` |
| `run(agent, prompt)` | `runtime.run(agent, prompt)` | same `AgentResult` shape: `result.output["result"]`, `print_result()` |
| `start(agent, prompt)` | `runtime.start(agent, prompt)` | returns handle with `.execution_id` |
| `stream(agent, prompt)` | `runtime.stream(agent, prompt)` | |
| `runtime.serve(agent, blocking=False)` | `runtime.serve(agent)` | worker process |
| `handle.get_status()` | `runtime.get_status(handle.execution_id)` | `status.status`, `.is_complete`, `.output["result"]` |
| `AgentHandle(workflow_id=…)` | reconnect via `execution_id` | naming change |
| `shutdown()` | `with AgentRuntime(…) as runtime:` | context-manager exit |
| `Strategy.HANDOFF` … | **identical** | all 9 members: HANDOFF (default), SEQUENTIAL, PARALLEL, ROUTER, ROUND_ROBIN, RANDOM, SWARM, MANUAL, PLAN_EXECUTE |
| `AGENTSPAN_SERVER_URL` | `CONDUCTOR_SERVER_URL` | plus `CONDUCTOR_AGENT_LLM_MODEL`, `CONDUCTOR_LOG_LEVEL` |

Multi-agent is untouched — this runs as-is after the import swap:

```python
support = Agent(
    name="support",
    model="openai/gpt-5.6-sol",
    instructions="Route each request to the right specialist.",
    agents=[billing, orders],
    strategy=Strategy.HANDOFF,
)
```

## 5. Framework agents (OpenAI SDK, LangGraph, ADK)

**OpenAI Agents SDK** — the bridge is one import. Your agent definition doesn't change:

```python
from agents import Agent, function_tool     # ← unchanged, the real OpenAI Agents SDK
from conductor.ai import Runner             # ← was: from agents import Runner

result = Runner.run_sync(billing, "What's the balance on account ACC-123?")
print(result.final_output)
```

Executed against the fused server: same answer, now with durable execution and a full trace in
the Conductor UI. (This bridge worked in Agentspan as `from agentspan import Runner` — only the
package root changes.)

**LangGraph** — same "pass it directly" model as Agentspan: build your graph natively
(`langchain.agents.create_agent` or a compiled `StateGraph`) and hand it to `runtime.run(graph, …)`.

**Google ADK** — pass your `SequentialAgent`/pipeline to `runtime.run(…)` as before. *(Adapter
installed by the `[agents]`/`[adk]` extra; not yet re-verified by us on 2.0.0 GA — if you hit an
issue, file it at [conductor-oss/conductor](https://github.com/conductor-oss/conductor/issues).)*

## 6. Not yet re-verified on 2.0.0

These Agentspan features exist in the fused SDK's public API but we have not re-run them against
GA at the time of writing — treat docs as authoritative and file issues on the Conductor repo:
memory (`ConversationMemory`/`SemanticMemory`), guardrails, termination conditions, the testing
utilities (`mock_run`/`MockEvent`/`expect`), `plan()`, and scheduling/`deploy()`.

## 7. Other languages

| Language | Status | Package |
|---|---|---|
| Python | ✅ full agent SDK | `conductor-python[agents]>=2.0.0` (PyPI) |
| TypeScript/JavaScript | ✅ full agent SDK | check the [SDK docs](https://orkes.io/content/category/sdks/) for the current npm package |
| Java | ✅ agent SDK, not yet on Maven Central | build from source in [conductor-oss/conductor](https://github.com/conductor-oss/conductor) |
| C# | ✅ full agent SDK | `conductor-ai` (NuGet) |
| Go / Rust / Ruby | workflow/worker clients only — no agent SDK | host tools as task workers |

## 8. Where everything lives now

- **Code + issues:** https://github.com/conductor-oss/conductor
- **Docs:** https://orkes.io/content/devguide/ai (agents) · https://orkes.io/content (all)
- **Quickstart:** https://orkes.io/content/quickstart/first-agent
- **This repo** is archived read-only. The final Agentspan release stays downloadable, existing
  installs keep working, and every question about the fused product belongs on the Conductor repo.

Thank you for building with Agentspan. The runtime lives on — it just wears the engine's name now.
