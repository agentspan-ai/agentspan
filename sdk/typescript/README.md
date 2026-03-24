# @agentspan/sdk

TypeScript SDK for building and running AI agents on [Agentspan](https://agentspan.dev). Define agents and tools in TypeScript, run them durably on Conductor with crash recovery, distributed workers, and human-in-the-loop approval.

## Features

- **89-feature parity** with the Python SDK
- **Superset tool system** — accepts Zod schemas, JSON Schema, and Vercel AI SDK tools
- **Framework passthrough** — run Vercel AI SDK, LangGraph.js, LangChain.js, OpenAI Agents, and Google ADK agents on Agentspan
- **Auto-detecting runtime** — `runtime.run()` accepts native agents and framework agents
- **Durable execution** — agents survive crashes and process failures
- **Human-in-the-loop** — approval workflows that pause for days, not minutes
- **Streaming** — real-time SSE event streaming with reconnection
- **Guardrails** — regex, LLM, and custom guardrails with retry/raise/fix/human modes
- **Testing framework** — mockRun, fluent assertions, record/replay, LLM judge

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

## Framework Passthrough

Run existing framework agents on Agentspan without any code changes:

```typescript
// Vercel AI SDK
import { generateText, tool as aiTool } from 'ai';
import { openai } from '@ai-sdk/openai';

const agent = {
  generate: (opts) => generateText({ model: openai('gpt-4o-mini'), tools: { weather: weatherTool }, ...opts }),
  stream: (opts) => streamText({ model: openai('gpt-4o-mini'), tools: { weather: weatherTool }, ...opts }),
  tools: { weather: weatherTool },
};

const result = await runtime.run(agent, 'What is the weather?');
// Auto-detected as Vercel AI SDK, runs via passthrough
```

```typescript
// LangGraph.js
import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';

const graph = createReactAgent({ llm: new ChatOpenAI({ model: 'gpt-4o-mini' }), tools: [searchTool] });
const result = await runtime.run(graph, 'Search for quantum computing');
```

```typescript
// OpenAI Agents SDK
import { Agent, run } from '@openai/agents';

const agent = new Agent({ name: 'helper', model: 'gpt-4o-mini', instructions: 'You are helpful.' });
const result = await runtime.run(agent, 'Hello!');
```

## Superset Tool System

Mix Zod schemas, JSON Schema, and Vercel AI SDK tools in the same agent:

```typescript
import { Agent, tool } from '@agentspan/sdk';
import { tool as aiTool } from 'ai';
import { z } from 'zod';

// Agentspan tool with Zod
const t1 = tool(fn, { inputSchema: z.object({ city: z.string() }) });

// Agentspan tool with JSON Schema
const t2 = tool(fn, { inputSchema: { type: 'object', properties: { city: { type: 'string' } } } });

// Vercel AI SDK tool (auto-detected)
const t3 = aiTool({ description: 'Search', inputSchema: z.object({ q: z.string() }), execute: fn });

// All three work together
const agent = new Agent({ name: 'test', tools: [t1, t2, t3] });
```

## Streaming

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

## Multi-Agent Strategies

```typescript
// Sequential pipeline
const pipeline = researcher.pipe(writer).pipe(editor);

// Parallel execution
const panel = new Agent({ name: 'panel', agents: [analyst1, analyst2], strategy: 'parallel' });

// Handoff (LLM decides)
const team = new Agent({ name: 'team', agents: [researcher, writer], strategy: 'handoff' });

// Router, round-robin, swarm, manual also available
```

## Guardrails

```typescript
import { guardrail, RegexGuardrail, LLMGuardrail } from '@agentspan/sdk';

const piiBlocker = new RegexGuardrail({
  name: 'pii_blocker',
  patterns: ['\\b\\d{3}-\\d{2}-\\d{4}\\b'],
  mode: 'block',
  onFail: 'retry',
});

const biasDetector = new LLMGuardrail({
  name: 'bias_detector',
  model: 'openai/gpt-4o-mini',
  policy: 'Check for biased language.',
  onFail: 'fix',
});

const agent = new Agent({ name: 'safe', guardrails: [piiBlocker, biasDetector], ... });
```

## Testing

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

Set environment variables or pass to `AgentRuntime` constructor:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:8080/api` | Server API URL |
| `AGENTSPAN_API_KEY` | — | Bearer token |
| `OPENAI_API_KEY` | — | For OpenAI models |

## Running Tests

```bash
# Unit tests only (no server needed)
npm test

# Full test suite with validation
AGENTSPAN_SERVER_URL=http://localhost:8080/api \
OPENAI_API_KEY=sk-... \
./scripts/test.sh
```

## Validation Framework

Run examples against a live server and validate with algorithmic checks + LLM judge:

```bash
# Smoke test (native agentspan examples)
npx tsx validation/runner.ts --config validation/runs.toml.example --run smoke --group SMOKE_TEST

# Framework comparison (native vs agentspan)
npx tsx validation/runner.ts --config validation/runs.toml.example --run vercel_ai --judge

# Generate HTML report
npx tsx validation/runner.ts --config validation/runs.toml.example --judge --report
```

## Examples

155 examples covering every feature:

| Category | Count | Framework |
|----------|-------|-----------|
| Native agentspan | 105 | — |
| LangGraph | 10 | `@langchain/langgraph` |
| LangChain | 10 | `@langchain/core` |
| OpenAI Agents | 10 | `@openai/agents` |
| Google ADK | 10 | `@google/adk` |
| Vercel AI SDK | 10 | `ai` |

```bash
# Run any example
npx tsx examples/01-basic-agent.ts
npx tsx examples/vercel-ai/01-passthrough.ts
npx tsx examples/langgraph/01-hello-world.ts
```

## API Reference

See the [design spec](../../docs/superpowers/specs/2026-03-23-typescript-sdk-design.md) for complete API documentation.

## License

MIT
