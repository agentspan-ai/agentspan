# SDK Conformance Checklist

Conformance of each SDK to `sdk-design-guide.md`. **Java is the reference
implementation.** Audited against source, not docs.

Legend: ✅ full · 🟡 partial · ❌ missing

| # | Feature | Java | Python | TypeScript | C# |
|---|---|:--:|:--:|:--:|:--:|
| 1 | Agent declarative config (name/model/instructions/maxTurns) | ✅ | ✅ | ✅ | ✅ |
| 2 | Dynamic instructions (callable, resolved at serialize) | ✅ | ✅ | ✅ | ✅ |
| 3 | Runtime: run/start/stream/plan/deploy/serve/resume/schedules + async | ✅ | ✅ | ✅ | ✅ |
| 4 | Env config: `AGENTSPAN_*` + worker tuning (poll, threads) | ✅ | ✅ | ✅ | ✅ |
| 5 | SSE streaming + 10 event types | ✅ | ✅ | ✅ | ✅ |
| 6 | HITL: approve/reject/respond + event-targeted sub-execution routing | ✅ | ✅ | ✅ | ✅ |
| 7 | All 9 strategies (handoff…plan_execute) | ✅ | ✅ | ✅ | ✅ |
| 8 | Built-in tools: HTTP/MCP/Human/Media/PDF/WaitForMessage/AgentTool/RAG | ✅ | ✅ | ✅ | ✅ |
| 9 | Custom tools: annotation + builder + discovery | ✅ | ✅ | ✅ | ✅ |
| 10 | Guardrails: custom/external/regex/LLM, position, onFail | ✅ | ✅ | ✅ | ✅ |
| 11 | Termination conditions, composable with and/or | ✅ | ✅ | ✅ | ✅ |
| 12 | Gate (text gate for sequential pipelines) | ✅ | ✅ | ✅ | ✅ |
| 13 | Handoffs: OnTextMention/OnToolResult/OnCondition + allowedTransitions | ✅ | ✅ | ✅ | ✅ |
| 14 | Plans (Plan/Step/Op/Ref/Generate/Validation/Context) | ✅ | ✅ | ✅ | ✅ |
| 15 | Schedules: builder + full lifecycle | ✅ | ✅ | ✅ | ✅ |
| 16 | Callbacks: before/after model & agent + composable tool hooks | ✅ | ✅ | ✅ | ✅ |
| 17 | Skills as agents | ✅ | ✅ | ✅ | ✅ |
| 18 | Agent-from-method annotations + `fromInstance` | ✅ | ✅ | ✅ | ✅ |
| 19 | Framework bridges (ecosystem-appropriate) | ✅ | ✅ | ✅ | ✅ |
| 20 | Stateful agents with per-execution domain (`runId`) | ✅ | ✅ | ✅ | ✅ |
| | **Score (✅ / 🟡 / ❌)** | **20 / 0 / 0** | **20 / 0 / 0** | **20 / 0 / 0** | **20 / 0 / 0** |

## Gaps closed (2026-06-21)

All four SDKs are now at full parity. The closure work and its deterministic e2e:

**Python** — event-targeted HITL (`approve`/`reject`/`respond`/`send` accept an
`event=` to target the WAITING event's sub-execution; top-level behavior
unchanged) (#6); `Agent.from_instance(obj)` / `from_instance(obj, name)` resolving
`@agent` methods with `@tool`/`@guardrail` attachment and by-name sub-agent wiring
(#18). Covered by e2e `test_suite23_from_instance_and_event_hitl.py` (23 tests).

**TypeScript** — `waitForMessageTool` (toolType `pull_workflow_messages`), matching
the Python/Java wire shape (#8). Covered by e2e Suite 22 + a unit test.

**C#** — `TextGate` (#12); handoff triggers `OnTextMention`/`OnToolResult`/
`OnCondition` evaluated in the swarm handoff-check worker (#13); callable
`InstructionsFn` resolved at serialize (#2); composable `CallbackHandler` +
agent/tool callbacks (#16); event-targeted `ApproveAsync(event)`/`RejectAsync(event)`
+ `IsWaitingAsync`/`WaitUntilWaitingAsync` (#6); `AGENTSPAN_WORKER_THREADS` /
`AGENTSPAN_WORKER_POLL_INTERVAL` (#4); `[AgentDef]` + `Agent.FromInstance` (#18).
Covered by e2e Suite 17 (deterministic).

Each closure followed the project's fail-first rule: a test was made to fail
(impl/assertion broken), the red confirmed, then restored to green.

## Notes

- **`CONDUCTOR_*` env vars** (`CONDUCTOR_SERVER_URL`/`AUTH_KEY`/`AUTH_SECRET`) are
  honored transitively by the Conductor SDK's `ApiClient` (the transport base each
  SDK builds on) — not a per-SDK gap. SDKs read `AGENTSPAN_*` as the explicit
  override. The env-config row (#4) reflects only SDK-level worker tuning.
- **Framework bridges** are intentionally ecosystem-specific and not directly
  comparable: Java (OpenAI/ADK/LangChain4j/LangGraph4j), Python (OpenAI/LangChain/
  LangGraph/Claude SDK), TypeScript (OpenAI/ADK/LangChain/LangGraph), C# (OpenAI/
  ADK/Semantic Kernel).
