# OpenAI Agents SDK + Agentspan

The OpenAI Agent format is natively recognized. Swap `run()` for `runtime.run()` — agent and tools stay identical.

## Before / After

<table>
<tr><th>Before (vanilla OpenAI Agents)</th><th>After (agentspan)</th></tr>
<tr><td>

```typescript
import { Agent, tool, run }
  from '@openai/agents';

import { z } from 'zod';

const getWeather = tool({
  name: 'get_weather',
  description: 'Get weather for a city.',
  parameters: z.object({
    city: z.string(),
  }),
  execute: async ({ city }) =>
    `72F, Sunny in ${city}`,
});

const agent = new Agent({
  name: 'weather_agent',
  instructions: 'You are helpful.',
  model: 'gpt-4o-mini',
  tools: [getWeather],
});



const result = await run(
  agent,
  'What is the weather in SF?',
);
console.log(result.finalOutput);
```

</td><td>

```typescript
import { Agent, tool, setTracingDisabled }
  from '@openai/agents';
// ^^^ replace run() with setTracingDisabled
import { z } from 'zod';
import { AgentRuntime } from '@agentspan-ai/sdk';
// ^^^ add agentspan import

const getWeather = tool({
  name: 'get_weather',
  description: 'Get weather for a city.',
  parameters: z.object({
    city: z.string(),
  }),
  execute: async ({ city }) =>
    `72F, Sunny in ${city}`,
});

const agent = new Agent({
  name: 'weather_agent',
  instructions: 'You are helpful.',
  model: 'gpt-4o-mini',
  tools: [getWeather],
});
// ^^^ agent definition is identical

setTracingDisabled(true); // optional
const runtime = new AgentRuntime();
const result = await runtime.run(
// ^^^ runtime.run() instead of run()
  agent,
  'What is the weather in SF?',
);
result.printResult();
await runtime.shutdown();
```

</td></tr>
</table>

### What changes — summary

| What | Change |
|------|--------|
| **Imports** | Drop `run` from `@openai/agents`, add `AgentRuntime` from `@agentspan-ai/sdk` |
| **Agent** | No changes — same `new Agent({ ... })` |
| **Tools** | No changes — same `tool({ ... })` |
| **Execution** | `run(agent, prompt)` → `runtime.run(agent, prompt)` |
| **Tracing** | Optional: `setTracingDisabled(true)` to avoid duplicate tracing |

## Examples

| File | Description |
|------|-------------|
| `01-basic-agent.ts` | Simple agent, no tools |
| `02-function-tools.ts` | Multiple tools with Zod schemas |
| `03-structured-output.ts` | Typed output |
| `04-handoffs.ts` | Multi-agent handoff (triage → specialists) |
| `05-guardrails.ts` | Input/output guardrails |
| `06-model-settings.ts` | Temperature, max tokens config |
| `07-streaming.ts` | Streaming output |
| `08-agent-as-tool.ts` | Nested agent as a tool |
| `09-dynamic-instructions.ts` | Runtime instruction generation |
| `10-multi-model.ts` | Different models per agent |

## Running

```bash
export AGENTSPAN_SERVER_URL=...
export OPENAI_API_KEY=...
cd sdk/typescript
npx tsx examples/openai/01-basic-agent.ts
```
