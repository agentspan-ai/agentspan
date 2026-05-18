# Vercel AI SDK + Agentspan

Two ways to integrate — pick what fits your stage.

## Quick start: one-line change

Swap one import. Your `generateText()` code stays identical.

<table>
<tr><th>Before (vanilla Vercel AI)</th><th>After (agentspan)</th></tr>
<tr><td>

```typescript
import { generateText, tool } from 'ai';
//      ^^^^^^^^^^^^
//      from 'ai'
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';

const weatherTool = tool({
  description: 'Get weather for a city',
  parameters: z.object({ city: z.string() }),
  execute: async ({ city }) => ({
    city, tempF: 62, condition: 'Foggy',
  }),
});

const result = await generateText({
  model: openai('gpt-4o-mini'),
  tools: { weather: weatherTool },
  system: 'You are a helpful assistant.',
  prompt: 'What is the weather in SF?',
});

console.log(result.text);
```

</td><td>

```typescript
import { generateText, tool } from '@agentspan-ai/sdk/vercel-ai';
//      ^^^^^^^^^^^^
//      from '@agentspan-ai/sdk/vercel-ai'  <-- only change
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';

const weatherTool = tool({
  description: 'Get weather for a city',
  parameters: z.object({ city: z.string() }),
  execute: async ({ city }) => ({
    city, tempF: 62, condition: 'Foggy',
  }),
});

const result = await generateText({
  model: openai('gpt-4o-mini'),
  tools: { weather: weatherTool },
  system: 'You are a helpful assistant.',
  prompt: 'What is the weather in SF?',
});

console.log(result.text);
```

</td></tr>
</table>

Everything else — tools, model, prompt, result shape — is unchanged. Under the hood, `generateText` builds an agentspan Agent, runs it on the platform, and maps the result back to the AI SDK format.

## Production: Agent API

When you need features that `generateText()` can't express — termination conditions, guardrails, multi-agent handoff, human-in-the-loop — use the Agent API directly.

<table>
<tr><th>Before (vanilla Vercel AI)</th><th>After (agentspan Agent API)</th></tr>
<tr><td>

```typescript
import { generateText, tool } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';

const weatherTool = tool({
  description: 'Get weather for a city',
  parameters: z.object({ city: z.string() }),
  execute: async ({ city }) => ({
    city, tempF: 62, condition: 'Foggy',
  }),
});

// No way to add guardrails,
// termination conditions, handoffs,
// or HITL approval here.

const result = await generateText({
  model: openai('gpt-4o-mini'),
  tools: { weather: weatherTool },
  system: 'You are a helpful assistant.',
  prompt: 'What is the weather in SF?',
});

console.log(result.text);
```

</td><td>

```typescript
import { tool as aiTool } from 'ai';
//                          ^^^ tools still from 'ai'
import { z } from 'zod';
import { Agent, AgentRuntime } from '@agentspan-ai/sdk';
//      ^^^^^  ^^^^^^^^^^^^
//      agentspan Agent + Runtime

const weatherTool = aiTool({
  description: 'Get weather for a city',
  parameters: z.object({ city: z.string() }),
  execute: async ({ city }) => ({
    city, tempF: 62, condition: 'Foggy',
  }),
});

const agent = new Agent({
  name: 'weather_agent',
  model: 'openai/gpt-4o-mini',
  //      ^^^^^^^^^^^^^^^^^^^ string, not provider object
  instructions: 'You are a helpful assistant.',
  tools: [weatherTool],
  //     ^ array, not Record — AI SDK tools auto-detected
});

const runtime = new AgentRuntime();
const result = await runtime.run(agent, 'What is the weather in SF?');
result.printResult();
await runtime.shutdown();
```

</td></tr>
</table>

### What the Agent API unlocks

| Feature | Example | How |
|---------|---------|-----|
| Termination conditions | `07-stop-conditions.ts` | `termination: new TextMention('DONE').or(new MaxMessage(10))` |
| Guardrails / middleware | `06-middleware.ts` | `guardrails: [new RegexGuardrail(...), guardrail(fn)]` |
| Multi-agent handoff | `08-agent-handoff.ts` | `agents: [specialist1, specialist2], strategy: 'handoff'` |
| Structured output | `04-structured-output.ts` | `outputType: z.object({ ... })` |
| Credential management | `09-credentials.ts` | `credentials: ['API_KEY']` |
| Human-in-the-loop | `10-hitl.ts` | `approvalRequired: true` on tools |
| Streaming events | `03-streaming.ts` | `runtime.run(agent, prompt)` with commented `runtime.stream(agent, prompt)` |

## Examples

| File | Description |
|------|-------------|
| `01-basic-agent.ts` | Simple agent with one AI SDK tool |
| `02-tools-compat.ts` | Mix of agentspan native and AI SDK tools |
| `03-streaming.ts` | Default `runtime.run()` flow with a commented `runtime.stream()` alternative |
| `04-structured-output.ts` | Zod schema for typed output |
| `05-multi-step.ts` | Multiple tools, multi-turn conversation |
| `06-middleware.ts` | Guardrails (regex + custom function) |
| `07-stop-conditions.ts` | Termination: TextMention + MaxMessage |
| `08-agent-handoff.ts` | Multi-agent with handoff strategy |
| `09-credentials.ts` | Server-managed credential injection |
| `10-hitl.ts` | Human approval before tool execution |

## Running

```bash
export AGENTSPAN_SERVER_URL=...
export OPENAI_API_KEY=...
cd sdk/typescript
npx tsx examples/vercel-ai/01-basic-agent.ts
```
