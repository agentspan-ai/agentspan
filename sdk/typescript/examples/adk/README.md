# Google ADK + Agentspan

The `LlmAgent` and `FunctionTool` formats are natively recognized. Replace the ADK runner with `runtime.run()` — agent and tools stay identical.

## Before / After

<table>
<tr><th>Before (vanilla Google ADK)</th><th>After (agentspan)</th></tr>
<tr><td>

```typescript
import { LlmAgent, FunctionTool }
  from '@google/adk';
import { z } from 'zod';



const getWeather = new FunctionTool({
  name: 'get_weather',
  description: 'Get weather for a city.',
  parameters: z.object({
    city: z.string(),
  }),
  execute: async (args: { city: string }) => ({
    city: args.city,
    temp_c: 22,
    condition: 'Clear',
  }),
});

const agent = new LlmAgent({
  name: 'weather_agent',
  model: 'gemini-2.5-flash',
  instruction: 'You are helpful.',
  tools: [getWeather],
});

// ADK runner / InMemoryRunner / session...
const runner = new InMemoryRunner(agent);
const session = await runner.sessionService
  .createSession({ appName: 'test' });
const events = runner.runAgent(
  session.id, 'Weather in Tokyo?',
);
for await (const event of events) {
  console.log(event);
}
```

</td><td>

```typescript
import { LlmAgent, FunctionTool }
  from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '@agentspan-ai/sdk';
// ^^^ add agentspan import

const getWeather = new FunctionTool({
  name: 'get_weather',
  description: 'Get weather for a city.',
  parameters: z.object({
    city: z.string(),
  }),
  execute: async (args: { city: string }) => ({
    city: args.city,
    temp_c: 22,
    condition: 'Clear',
  }),
});

const agent = new LlmAgent({
  name: 'weather_agent',
  model: 'gemini-2.5-flash',
  instruction: 'You are helpful.',
  tools: [getWeather],
});
// ^^^ agent + tools are identical

const runtime = new AgentRuntime();
const result = await runtime.run(
// ^^^ runtime.run() instead of ADK runner
  agent,
  'Weather in Tokyo?',
);
result.printResult();
await runtime.shutdown();
```

</td></tr>
</table>

### What changes — summary

| What | Change |
|------|--------|
| **Imports** | Add `AgentRuntime` from `@agentspan-ai/sdk` |
| **Agent** | No changes — same `new LlmAgent({ ... })` |
| **Tools** | No changes — same `new FunctionTool({ ... })` |
| **Execution** | ADK runner → `runtime.run(agent, prompt)` |

## Examples

| File | Description |
|------|-------------|
| `00-hello-world.ts` | Minimal agent, no tools |
| `01-basic-agent.ts` | Agent with instructions |
| `02-function-tools.ts` | Multiple FunctionTool instances |
| `03-structured-output.ts` | Typed output schemas |
| `04-sub-agents.ts` | Nested sub-agents |
| `05-generation-config.ts` | Temperature, top-p, max tokens |
| `06-streaming.ts` | Streaming output |
| `07-output-key-state.ts` | Output key and state management |
| `08-instruction-templating.ts` | Dynamic instruction templates |
| `09-multi-tool-agent.ts` | Agent with many tools |

## Running

```bash
export AGENTSPAN_SERVER_URL=...
# For Gemini models:
export GOOGLE_API_KEY=...
# Or override with OpenAI:
export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
export OPENAI_API_KEY=...

cd sdk/typescript
npx tsx examples/adk/01-basic-agent.ts
```
