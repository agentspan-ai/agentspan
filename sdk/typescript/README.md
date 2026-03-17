# Agentspan JS SDK

JavaScript SDK for building and running AI agents on [Conductor](https://github.com/conductor-oss/conductor). Define agents and tools in plain JavaScript (or TypeScript), run them durably on Conductor.

- **JavaScript-first** — no build step required, CommonJS out of the box
- **TypeScript support** — type definitions included; optional `@AgentTool` class decorator
- **Conductor workers** — tool functions run as distributed Conductor tasks via [`@io-orkes/conductor-javascript`](https://github.com/conductor-oss/javascript-sdk)
- **Same wire format** as the [Python SDK](../agentspan/sdk/python) — share agents across languages

---

## Installation

```bash
npm install
```

Requires **Node 18+** (uses native `fetch`).

---

## Quick start

```js
const { Agent, AgentRuntime, tool } = require('@agentspan/sdk')

const getWeather = tool(
  async function getWeather({ city }) {
    return { city, temperature_f: 72, condition: 'Sunny' }
  },
  {
    description: 'Get the current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: { city: { type: 'string' } },
      required: ['city'],
    },
  }
)

const agent = new Agent({
  name: 'weather_agent',
  model: 'openai/gpt-4o',
  instructions: 'You are a helpful weather assistant.',
  tools: [getWeather],
})

const runtime = new AgentRuntime({ serverUrl: 'http://localhost:8080' })
const result = await runtime.run(agent, "What's the weather in SF?")
result.printResult()
await runtime.shutdown()
```

---

## Configuration

Set environment variables (or create a `.env` file — `dotenv` is auto-loaded in examples):

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:8080/api` | Conductor server URL |
| `AGENTSPAN_AUTH_KEY` | — | Auth key (Orkes Cloud only) |
| `AGENTSPAN_AUTH_SECRET` | — | Auth secret (Orkes Cloud only) |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | `100` | Worker poll interval (ms) |
| `AGENTSPAN_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARN` / `ERROR` |
| `AGENT_LLM_MODEL` | — | Model in `provider/model` format, e.g. `openai/gpt-4o` |

```bash
cp .env.example .env
# then edit .env
```

---

## API reference

### `tool(fn, options)`

Wraps a function as an agent tool. The function receives a single `input` object matching the `inputSchema` and should return a plain object (or a value that will be wrapped in `{ result }`).

```js
const myTool = tool(
  async function myTool({ x, y }) {
    return { sum: x + y }
  },
  {
    name: 'my_tool',            // optional — defaults to function name
    description: 'Add two numbers.',
    inputSchema: {
      type: 'object',
      properties: {
        x: { type: 'number' },
        y: { type: 'number' },
      },
      required: ['x', 'y'],
    },
    approvalRequired: false,    // set true for human-in-the-loop
    timeoutSeconds: 30,         // optional
  }
)
```

#### Server-side tools (no local worker)

```js
const { httpTool, mcpTool } = require('@agentspan/sdk')

// HTTP tool — Conductor calls the endpoint directly
const weatherApi = httpTool({
  name: 'get_weather',
  description: 'Fetch live weather data.',
  url: 'https://api.weather.example.com/current',
  method: 'GET',
  inputSchema: {
    type: 'object',
    properties: { city: { type: 'string' } },
    required: ['city'],
  },
})

// MCP tool — routes through an MCP server
const githubTools = mcpTool({
  name: 'github_mcp',
  description: 'GitHub tools via MCP.',
  serverUrl: 'http://localhost:3001/mcp',
})
```

---

### `new Agent(options)`

```js
const agent = new Agent({
  name: 'my_agent',           // required — unique name, becomes the workflow name
  model: 'openai/gpt-4o',     // 'provider/model' format
  instructions: 'You are...', // system prompt (string or () => string)
  tools: [myTool],            // tool() wrappers, httpTool/mcpTool defs, or toolsFrom() output
  maxTurns: 25,               // max LLM iterations (default: 25)
  temperature: 0,             // optional
  maxTokens: 4096,            // optional
})
```

#### Multi-agent

```js
const researcher = new Agent({ name: 'researcher', model: 'openai/gpt-4o', tools: [search] })
const writer     = new Agent({ name: 'writer',     model: 'openai/gpt-4o' })

// Handoff — LLM decides which sub-agent to call
const coordinator = new Agent({
  name: 'coordinator',
  model: 'openai/gpt-4o',
  agents: [researcher, writer],
  strategy: 'handoff',
})

// Sequential pipeline — output of each step feeds the next
const pipeline = new Agent({
  name: 'pipeline',
  agents: [researcher, writer],
  strategy: 'sequential',
})

// Parallel — all sub-agents run concurrently
const panel = new Agent({
  name: 'panel',
  agents: [researcher, writer],
  strategy: 'parallel',
})
```

---

### `new AgentRuntime(options)`

```js
const runtime = new AgentRuntime({
  serverUrl: 'http://localhost:8080', // auto-appends /api if missing
  authKey: '...',                     // optional
  authSecret: '...',                  // optional
  logLevel: 'INFO',
})
```

#### `runtime.run(agent, prompt, [options])` → `AgentResult`

Blocks until the workflow completes.

```js
const result = await runtime.run(agent, "What's the weather in SF?")

console.log(result.output)        // { result: "The weather in SF is..." }
console.log(result.status)        // 'COMPLETED'
console.log(result.toolCalls)     // [{ name, args, result }, ...]
console.log(result.isSuccess)     // true
result.printResult()              // pretty-print to stdout
```

#### `runtime.start(agent, prompt, [options])` → `AgentHandle`

Fire-and-forget — returns a handle immediately.

```js
const handle = await runtime.start(agent, 'Long running task...')

console.log(handle.workflowId)

// Poll status
const status = await handle.getStatus()
// { isComplete, isRunning, isWaiting, status, output, ... }

// Block until done
const result = await handle.wait()

// Human-in-the-loop approval (when isWaiting === true)
await handle.approve()
await handle.reject('Too risky')
```

#### `runtime.stream(agent, prompt, [options])` → `AsyncIterable<AgentEvent>`

Stream events as they happen.

```js
for await (const event of runtime.stream(agent, prompt)) {
  switch (event.type) {
    case 'thinking':
      console.log('thinking:', event.content)
      break
    case 'tool_call':
      console.log(`calling ${event.toolName}(`, event.args, ')')
      break
    case 'tool_result':
      console.log(`${event.toolName} returned`, event.result)
      break
    case 'waiting':
      // approval-required tool is paused — use handle.approve() / handle.reject()
      break
    case 'error':
      console.error('error:', event.error)
      break
    case 'done':
      console.log('output:', event.output)
      break
  }
}
```

#### `runtime.plan(agent)` → workflow definition JSON

Compile an agent to a Conductor workflow definition without running it.

```js
const workflowDef = await runtime.plan(agent)
console.log(JSON.stringify(workflowDef, null, 2))
```

#### `runtime.shutdown()`

Stop all workers cleanly.

```js
await runtime.shutdown()
```

---

## TypeScript — `@AgentTool` decorator

For TypeScript projects, you can define tools as decorated class methods instead of using `tool()`. The decorator is a method decorator only (TypeScript/JavaScript limitation — standalone function decorators are not supported).

```ts
import { AgentTool, toolsFrom } from '@agentspan/sdk/decorators'
const { Agent, AgentRuntime } = require('@agentspan/sdk')

class WeatherTools {
  @AgentTool({
    description: 'Get the current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: { city: { type: 'string' } },
      required: ['city'],
    },
  })
  async getWeather({ city }: { city: string }) {
    return { city, temperature_f: 58, condition: 'Foggy' }
  }

  @AgentTool({
    description: 'Evaluate a math expression.',
    inputSchema: {
      type: 'object',
      properties: { expression: { type: 'string' } },
      required: ['expression'],
    },
  })
  async calculate({ expression }: { expression: string }) {
    return { expression, result: eval(expression) }
  }
}

// toolsFrom() extracts all @AgentTool-decorated methods as tool() wrappers
const agent = new Agent({
  name: 'my_agent',
  model: 'openai/gpt-4o',
  tools: toolsFrom(new WeatherTools()),
})
```

Build the decorator module before use:

```bash
npm run build:decorators
```

Or run directly with ts-node:

```bash
npx ts-node --project decorators/tsconfig.json examples/weather-decorators.ts
```

> **Note:** Requires `"experimentalDecorators": true` in your `tsconfig.json`.

---

## Examples

```bash
# Plain JS weather example
AGENTSPAN_SERVER_URL=http://localhost:8080 \
AGENT_LLM_MODEL=openai/gpt-4o \
node examples/weather.js

# Custom prompt
node examples/weather.js "What's the weather in Tokyo and London?"

# Streaming events
node examples/weather-stream.js "What's the weather in Miami?"

# TypeScript @AgentTool decorator
npx ts-node --project decorators/tsconfig.json examples/weather-decorators.ts
```

---

## Project structure

```
agentspan-js/
├── src/
│   ├── index.js          # Public API
│   ├── agent.js          # Agent class
│   ├── tool.js           # tool(), httpTool(), mcpTool()
│   ├── runtime.js        # AgentRuntime
│   ├── config.js         # AgentConfig (env var loading)
│   ├── result.js         # AgentResult, AgentHandle, AgentEvent
│   ├── serializer.js     # Agent → AgentConfig JSON
│   └── worker-manager.js # Conductor TaskManager wrapper
├── decorators/
│   ├── index.ts          # @AgentTool + toolsFrom() (TypeScript)
│   └── tsconfig.json
├── types/
│   └── index.d.ts        # TypeScript type definitions
├── examples/
│   ├── weather.js             # Plain JS example
│   ├── weather-stream.js      # Streaming events
│   └── weather-decorators.ts  # TypeScript decorator example
├── js-sdk-plan.md
├── .env.example
└── package.json
```
