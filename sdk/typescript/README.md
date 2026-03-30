# @agentspan/sdk

[![npm](https://img.shields.io/npm/v/@agentspan/sdk)](https://www.npmjs.com/package/@agentspan/sdk)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../../LICENSE)

TypeScript SDK for building and running AI agents on [Agentspan](https://agentspan.dev). Define agents and tools in TypeScript, run them durably on the platform with crash recovery, distributed workers, and human-in-the-loop approval.

## Quick Start

```bash
npm install @agentspan/sdk zod
```

```typescript
import { Agent, AgentRuntime, tool } from '@agentspan/sdk';
import { z } from 'zod';

const getWeather = tool(
  async ({ city }: { city: string }) => ({ city, temp: 72, condition: 'Sunny' }),
  {
    description: 'Get current weather for a city.',
    inputSchema: z.object({ city: z.string() }),
  },
);

const agent = new Agent({
  name: 'weather_agent',
  model: 'openai/gpt-4o',
  instructions: 'You are a helpful weather assistant.',
  tools: [getWeather],
});

const runtime = new AgentRuntime();
const result = await runtime.run(agent, "What's the weather in SF?");
result.printResult();
await runtime.shutdown();
```

## Already using Vercel AI SDK?

One import change. Your code stays identical.

```diff
-import { generateText } from 'ai';
+import { generateText } from '@agentspan/sdk/vercel-ai';
```

That's it. `generateText` and `streamText` are intercepted, compiled to an agent execution, and run on Agentspan. Tools, model, prompt, result shape -- all unchanged.

When you need Agentspan-specific features (guardrails, termination, multi-agent handoff), switch to the Agent API. See [`examples/vercel-ai/README.md`](examples/vercel-ai/README.md) for the full before/after.

## Already using another framework?

Pass your existing agent objects directly to `runtime.run()`:

<table>
<tr><th>Framework</th><th>Integration</th></tr>
<tr><td><b>OpenAI Agents</b></td><td>

```typescript
import { Agent } from '@openai/agents';
import { AgentRuntime } from '@agentspan/sdk';

const agent = new Agent({
  name: 'helper', model: 'gpt-4o-mini',
  instructions: 'You are helpful.',
  tools: [getWeather],
});
// Agent format auto-detected
const runtime = new AgentRuntime();
await runtime.run(agent, 'Weather in SF?');
```

</td></tr>
<tr><td><b>Google ADK</b></td><td>

```typescript
import { LlmAgent } from '@google/adk';
import { AgentRuntime } from '@agentspan/sdk';

const agent = new LlmAgent({
  name: 'helper', model: 'gemini-2.5-flash',
  instruction: 'You are helpful.',
  tools: [getWeather],
});
// Agent format auto-detected
const runtime = new AgentRuntime();
await runtime.run(agent, 'Weather in Tokyo?');
```

</td></tr>
<tr><td><b>LangGraph</b></td><td>

```typescript
import { createReactAgent }
  from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { AgentRuntime } from '@agentspan/sdk';

const graph = createReactAgent({
  llm: new ChatOpenAI({ model: 'gpt-4o-mini' }),
  tools: [searchTool],
});
// Add metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [searchTool],
  framework: 'langgraph',
};
const runtime = new AgentRuntime();
await runtime.run(graph, 'Search quantum');
```

</td></tr>
</table>

See per-framework READMEs for complete before/after guides:
[Vercel AI](examples/vercel-ai/README.md) | [OpenAI](examples/openai/README.md) | [Google ADK](examples/adk/README.md) | [LangGraph](examples/langgraph/README.md) | [LangChain](examples/langchain/README.md)

## Features

### Streaming

```typescript
const stream = await runtime.stream(agent, prompt);

for await (const event of stream) {
  switch (event.type) {
    case 'thinking':    console.log(event.content); break;
    case 'tool_call':   console.log(event.toolName, event.args); break;
    case 'tool_result': console.log(event.toolName, event.result); break;
    case 'waiting':     await stream.approve(); break;
    case 'done':        console.log(event.output); break;
  }
}
```

### Multi-Agent Strategies

```typescript
// Sequential pipeline
const pipeline = researcher.pipe(writer).pipe(editor);

// Parallel (scatter-gather)
const panel = new Agent({ name: 'panel', agents: [analyst1, analyst2], strategy: 'parallel' });

// Handoff (LLM decides which specialist to route to)
const team = new Agent({ name: 'team', agents: [coder, reviewer], strategy: 'handoff' });

// Also: router, round-robin, swarm, manual
```

### Guardrails

```typescript
import { guardrail, RegexGuardrail, LLMGuardrail } from '@agentspan/sdk';

const piiBlocker = new RegexGuardrail({
  name: 'pii_blocker',
  patterns: ['\\b\\d{3}-\\d{2}-\\d{4}\\b'],
  mode: 'block', onFail: 'raise',
});

const customCheck = guardrail(
  async (content: string) => {
    if (content.includes('secret')) return { passed: false, message: 'Sensitive content' };
    return { passed: true };
  },
  { name: 'custom_check', position: 'output', onFail: 'retry' },
);

const agent = new Agent({ name: 'safe', guardrails: [piiBlocker, customCheck], ... });
```

### Human-in-the-Loop

```typescript
const handle = await runtime.start(agent, prompt);

// Agent pauses when it hits a tool with approvalRequired: true
const status = await handle.getStatus();
if (status.isWaiting) {
  await handle.approve();   // or handle.reject('reason')
}

const result = await handle.wait();
```

### Termination Conditions

```typescript
import { TextMention, MaxMessage } from '@agentspan/sdk';

const agent = new Agent({
  name: 'analyst',
  termination: new TextMention('DONE').or(new MaxMessage(10)),
  ...
});
```

### Testing

```typescript
import { mockRun, expectResult } from '@agentspan/sdk/testing';

const result = await mockRun(agent, 'Write an article', {
  mockTools: { search: async () => ({ results: ['paper1'] }) },
});

expectResult(result)
  .toBeCompleted()
  .toContainOutput('article')
  .toHaveUsedTool('search');
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Server API URL |
| `AGENTSPAN_API_KEY` | -- | Bearer token |
| `OPENAI_API_KEY` | -- | For OpenAI models |

All config can also be passed to the `AgentRuntime` constructor.

## Examples

157 examples covering every feature:

| Directory | Count | Description |
|-----------|-------|-------------|
| [`examples/`](examples/) | 107 | Native Agentspan agents |
| [`examples/vercel-ai/`](examples/vercel-ai/) | 10 | Vercel AI SDK integration |
| [`examples/langgraph/`](examples/langgraph/) | 10 | LangGraph integration |
| [`examples/langchain/`](examples/langchain/) | 10 | LangChain integration |
| [`examples/openai/`](examples/openai/) | 10 | OpenAI Agents SDK integration |
| [`examples/adk/`](examples/adk/) | 10 | Google ADK integration |

```bash
npx tsx examples/01-basic-agent.ts
npx tsx examples/vercel-ai/01-basic-agent.ts
npx tsx examples/langgraph/02-react-with-tools.ts
```

## Contributing

We welcome contributions! Please open an issue or PR on [GitHub](https://github.com/agentspan/agentspan).

```bash
git clone https://github.com/agentspan/agentspan.git
cd agentspan/sdk/typescript
npm install
npm test        # unit tests (no server needed)
npm run lint    # type-check
```

## License

MIT
