# Agentspan TypeScript SDK — Documentation

The official TypeScript/Node SDK for [Agentspan](https://agentspan.ai) — durable, scalable, observable AI agents.

- **Package:** `@agentspan-ai/sdk` (npm)
- **Runtime:** Node.js >= 18
- **Module:** ESM and CommonJS (`import` / `require`)

## Contents

| Doc | Covers |
|---|---|
| [getting-started.md](getting-started.md) | Install, env vars, and a running agent in under 30 seconds. |
| [writing-agents.md](writing-agents.md) | Authoring agents: instructions, tools, multi-agent strategies, handoffs, guardrails, termination, callbacks, streaming, HITL, schedules, agent-from-method, stateful agents. |
| [framework-agents.md](framework-agents.md) | Running agents authored with OpenAI, Google ADK, LangChain, LangGraph, and the Vercel AI SDK. |
| [advanced.md](advanced.md) | Runtime config, the `AgentClient` control plane, the `WorkflowClient`, deploy/serve/run/plan, structured output, credentials, plans / PLAN_EXECUTE, skills. |
| [api-reference.md](api-reference.md) | The public surface, one section per type. |

## At a glance

```ts
import { Agent, AgentRuntime } from '@agentspan-ai/sdk';

const agent = new Agent({
  name: 'greeter',
  model: 'openai/gpt-4o-mini',
  instructions: 'You are a friendly assistant. Keep responses brief.',
});

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(agent, 'Say hello!');
  result.printResult();
} finally {
  await runtime.shutdown();
}
```

You need a running Agentspan server (default `http://localhost:6767/api`). See [getting-started.md](getting-started.md).
