# Framework Agents

You don't have to rewrite agents authored with another framework to run them on Agentspan. The runtime **detects** the framework object you pass to `run()` / `deploy()` / `stream()`, serializes it to an agent config, and runs it on the server — same call you'd make with a native `Agent`.

```ts
const runtime = new AgentRuntime();
const result = await runtime.run(frameworkAgent, prompt);   // <-- same entry point
```

Supported frameworks: **OpenAI Agents SDK**, **Google ADK**, **LangChain**, **LangGraph**, and the **Vercel AI SDK**. Detection is pure duck-typing — no framework is imported by the SDK. The framework packages are optional peer dependencies; install whichever you use.

## How detection works

`runtime.run(agent, ...)` calls `detectFramework(agent)`. It returns the first match:

| Framework | Detected when the object has… |
|---|---|
| native `Agent` | is an instance of `Agent` (runs natively, not as a framework) |
| `langgraph` | `.invoke()` plus a graph shape (`.getGraph()`, a `.nodes` Map, or `.nodes` + `.builder`) |
| `langchain` | `.invoke()` plus an `lc_namespace` array (e.g. an `AgentExecutor`) |
| `openai` | `name` + string/function `instructions` + string `model` + `tools[]` + an OpenAI marker (`handoffs[]`, `inputGuardrails[]`, `asTool()`, `toolUseBehavior`, ...) |
| `google_adk` | `subAgents[]` (orchestration agents), or string `model` + ADK markers (`instruction`, `outputKey`, `generateContentConfig`, `beforeModelCallback`, ...) |

If nothing matches and the object isn't a native `Agent`, you get a clear error.

## OpenAI Agents SDK

Pass an `@openai/agents` `Agent` straight to the runtime.

```ts
import { Agent, setTracingDisabled } from '@openai/agents';
import { AgentRuntime } from '@conductoross/conductor-agent-sdk';

setTracingDisabled(true);

const agent = new Agent({
  name: 'greeter',
  instructions: 'You are a friendly assistant. Keep your responses concise and helpful.',
  model: 'gpt-4o-mini',
});

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(agent, 'Say hello and tell me a fun fact about TypeScript.');
  result.printResult();
} finally {
  await runtime.shutdown();
}
```

## Google ADK

Pass a `@google/adk` agent (`LlmAgent`, or the `Sequential`/`Parallel`/`Loop` orchestration agents).

```ts
import { LlmAgent } from '@google/adk';
import { AgentRuntime } from '@conductoross/conductor-agent-sdk';

const agent = new LlmAgent({
  name: 'greeter',
  model: 'gemini-2.5-flash',
  instruction: 'You are a friendly assistant. Keep your responses concise and helpful.',
});

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(agent, 'Say hello and tell me a fun fact about ML.');
  result.printResult();
} finally {
  await runtime.shutdown();
}
```

## LangGraph

Pass a prebuilt `createReactAgent` graph directly — detection handles it via `.invoke()` + graph shape.

```ts
import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { AgentRuntime } from '@conductoross/conductor-agent-sdk';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const graph = createReactAgent({ llm, tools, name: 'math_agent' });

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(graph, 'What is 12 * 9?');
  result.printResult();
} finally {
  await runtime.shutdown();
}
```

For a complex graph where automatic introspection of the model/tools could fail, import `createReactAgent` from the SDK wrapper instead. It stamps `._agentspan` metadata onto the graph so the serializer skips introspection:

```ts
import { createReactAgent } from '@conductoross/conductor-agent-sdk/langgraph';
```

You can also pass a model hint at call time when detection can't infer it: `runtime.run(graph, prompt, { model: 'openai/gpt-4o-mini' })`.

## LangChain

A real `langchain` `AgentExecutor` is detected via `.invoke()` + `lc_namespace`. To make the model/tools unambiguous, use the SDK's drop-in builder, which attaches `._agentspan` metadata:

```ts
import { createAgentExecutor } from '@conductoross/conductor-agent-sdk/langchain';
import { AgentRuntime } from '@conductoross/conductor-agent-sdk';

const executor = createAgentExecutor({ agent, tools, llm });

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(executor, 'Summarize the latest release notes.');
  result.printResult();
} finally {
  await runtime.shutdown();
}
```

The `@conductoross/conductor-agent-sdk/langchain` subpath also exports `createRunnableWithMetadata(...)` (a runnable-like object with `invoke` + `lc_namespace` + metadata) and `getLangChainModule()`.

## Vercel AI SDK

Two ways to use the AI SDK:

**1. AI SDK tools on a native Agent (recommended).** The tool system is a superset — it auto-detects AI SDK `tool()` objects (Zod `parameters` + `execute`) and converts them to native tool defs. No wrapper needed.

```ts
import { tool as aiTool } from 'ai';
import { z } from 'zod';
import { Agent, AgentRuntime } from '@conductoross/conductor-agent-sdk';

const weatherTool = aiTool({
  description: 'Get current weather for a city',
  parameters: z.object({ city: z.string().describe('City name') }),
  execute: async ({ city }) => ({ city, tempF: 62, condition: 'Foggy' }),
});

const agent = new Agent({
  name: 'weather_agent',
  model: 'openai/gpt-4o-mini',
  instructions: 'Use available tools to answer questions.',
  tools: [weatherTool],
});

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(agent, 'What is the weather in San Francisco?');
  result.printResult();
} finally {
  await runtime.shutdown();
}
```

**2. Drop-in `generateText` / `streamText`.** The `@conductoross/conductor-agent-sdk/vercel-ai` subpath exports AI-SDK-shaped `generateText` and `streamText` that internally build an `Agent` + `AgentRuntime` and map the result back into the AI SDK response shape:

```ts
import { generateText } from '@conductoross/conductor-agent-sdk/vercel-ai';

const { text } = await generateText({
  model: 'openai/gpt-4o-mini',
  prompt: 'Write a haiku about durable execution.',
});
```

## Notes

- All five frameworks use the identical `runtime.run(agentOrGraph, prompt)` entry point — there is no per-framework runtime API.
- Framework peer deps (`@openai/agents`, `@google/adk`, `@langchain/*`, `ai`, `zod`) are optional; install only what you use. The wrappers lazy-load their dependency and throw an install hint if it's missing.
- Framework agents can be deployed too: `runtime.deploy(frameworkAgent)`. See [advanced.md](advanced.md).
