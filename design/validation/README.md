# Validation & E2E — Methodology

**Status:** Consolidated 2026-06-26

**Scope:** How the Agentspan SDKs are validated. This is the cross-cutting overview;
each SDK has its own doc with the concrete suites, commands, and CI wiring. For how
each SDK is built, see the [reference implementations](../sdk-design/languages/);
for the SDK contract being validated, see [sdk-design.md](../sdk-design.md).

## Two complementary approaches

| Approach | What it proves | LLM judge? | SDKs |
|---|---|---|---|
| **Deterministic E2E suites** | The SDK compiles + executes real agents against a real server correctly | **No** — assertions are deterministic (`plan()` structure, workflow-task status, Conductor API side-effects) | Python, TypeScript, Java, C# (all 4) |
| **Examples-quality validation framework** | Ported examples behave correctly across models, and Agentspan-compiled execution matches native-framework execution | **Yes** — an LLM judge scores semantic quality | Python, TypeScript |

The determinism rule is a project constraint (see `CLAUDE.md`): **e2e must not use
LLM-as-judge** except where the explicit purpose is judging quality/output/evals. The
examples-quality framework is the only place a judge appears.

## Shared harness

All e2e runs exercise the **real stack** — no mocks:
- The **Agentspan server** jar on `:6767` (`conductor-agentspan-server/build/libs/agentspan-runtime.jar`).
- **mcp-testkit** for HTTP/MCP tool endpoints (test infra only — never an SDK dependency).
- Credentials managed via the `agentspan` CLI / the server secrets API (never read from the worker env).
- Config via `AGENTSPAN_SERVER_URL`, `AGENTSPAN_CLI_PATH`, `AGENTSPAN_LLM_MODEL` (model defaults to `openai/gpt-4o-mini`).

## Per-SDK validation docs

| SDK | Doc | E2E suites | Quality framework |
|---|---|---|---|
| Python | [python-validation.md](python-validation.md) | ✅ `sdk/python/e2e/` | ✅ `sdk/python/validation/` |
| TypeScript | [typescript-validation.md](typescript-validation.md) | ✅ `sdk/typescript/tests/e2e/` | ✅ `sdk/typescript/validation/` |
| Java | [java-validation.md](java-validation.md) | ✅ `sdk/java/e2e/` | — |
| C# | [csharp-validation.md](csharp-validation.md) | ✅ `sdk/csharp/tests/AgentspanE2eTests/` | — |

Each per-SDK doc is cross-linked from that SDK's
[reference implementation](../sdk-design/languages/) "Testing" section.
