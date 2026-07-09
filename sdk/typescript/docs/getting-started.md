# Getting Started

Get an agent running in under 30 seconds.

## 1. Install

The SDK ships as the `@conductor-oss/conductor-agent-sdk` npm package (Node.js >= 18).

```bash
npm install @conductor-oss/conductor-agent-sdk
```

It is published as both ESM and CommonJS, so `import` and `require` both work. The examples in these docs use ESM (`import`). You will also want `zod` if you plan to define tool/output schemas with it:

```bash
npm install zod
```

## 2. Point at a server

You need a running Agentspan server. The defaults assume a local one at `http://localhost:6767/api` (the SDK auto-appends `/api` if you omit it).

| Variable | Default | Description |
|---|---|---|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Agentspan server URL. |
| `AGENTSPAN_AUTH_KEY` | — | Auth key. Unset = no-auth mode (local / OSS). |
| `AGENTSPAN_AUTH_SECRET` | — | Auth secret. Set together with the key for Orkes Cloud. |
| `AGENTSPAN_API_KEY` | — | Pre-minted bearer token (alternative to key/secret). |

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export OPENAI_API_KEY=<YOUR-KEY>
export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
# Orkes Cloud only:
# export AGENTSPAN_AUTH_KEY=...
# export AGENTSPAN_AUTH_SECRET=...
```

`AGENTSPAN_AUTH_KEY` / `AGENTSPAN_AUTH_SECRET` are minted into a short-lived JWT and sent as the `X-Authorization` header on every server call. The SDK handles that for you — you only set the env vars. The SDK loads a `.env` file automatically (via `dotenv`).

A handful of other env vars tune workers and logging (`AGENTSPAN_WORKER_POLL_INTERVAL`, `AGENTSPAN_WORKER_THREADS`, `AGENTSPAN_LOG_LEVEL`, ...); see [advanced.md](advanced.md#runtime-configuration).

## 3. Run an agent

```ts
import { Agent, AgentRuntime } from '@conductor-oss/conductor-agent-sdk';

const agent = new Agent({
  name: 'greeter',
  model: 'anthropic/claude-sonnet-4-6',
  instructions: 'You are a friendly assistant. Keep responses brief.',
});

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(agent, 'Say hello and tell me a fun fact about TypeScript.');
  result.printResult();
} finally {
  await runtime.shutdown();
}
```

Run it with `tsx` (or compile + `node`):

```bash
npx tsx my-agent.ts
```

That is the whole loop: define an `Agent`, create an `AgentRuntime`, `await runtime.run(agent, prompt)`, and read the `AgentResult`. `runtime.shutdown()` stops any local tool-worker polling so the process can exit.

## Reading the result

`run()` returns an [`AgentResult`](api-reference.md#agentresult). Common members:

```ts
result.printResult();                  // formatted summary to stdout
const ok       = result.isSuccess;     // status === 'COMPLETED'
const output   = result.output;        // Record<string, unknown>; final text is usually output.result
const tokens   = result.tokenUsage;    // { promptTokens, completionTokens, totalTokens } | undefined
const finish   = result.finishReason;  // 'stop' | 'length' | 'guardrail' | 'rejected' | ...
const execId   = result.executionId;   // durable execution id on the server
```

`output` is always a `Record`. A plain text answer arrives as `{ result: "..." }`; structured output (see [advanced.md](advanced.md#structured-output)) arrives under `output.result` as an object.

## Next

- [writing-agents.md](writing-agents.md) — tools, multi-agent orchestration, guardrails, streaming, HITL, schedules.
- [framework-agents.md](framework-agents.md) — run OpenAI / ADK / LangChain / LangGraph / Vercel AI agents as-is.
- [advanced.md](advanced.md) — deploy/serve, the control-plane `AgentClient`, structured output, credentials.
