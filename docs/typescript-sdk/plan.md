# Agentspan JavaScript SDK — Plan

## Guiding Principles

| Principle | Decision |
|-----------|----------|
| Primary language | **JavaScript** (`.js` CommonJS), no build step required |
| TypeScript support | **Optional** — `@AgentTool` decorator in `decorators/index.ts`, type definitions in `types/index.d.ts` |
| Tool definition | `tool(fn, options)` wrapper function — mirrors Python's `@tool` decorator |
| TS decorator alternative | Class-based `@AgentTool` + `toolsFrom()` (TypeScript only, no standalone function decorator possible in JS/TS) |
| Conductor workers | `@io-orkes/conductor-javascript` `TaskManager` for polling and task dispatch |
| HTTP transport | Native `fetch` (Node 18+) |
| Config | `process.env` with `AGENTSPAN_` prefix, `.env` file support via `dotenv` |
| Wire format | Identical `AgentConfig` JSON structure as Python SDK — same server endpoint |

---

## Package Structure

```
js/
├── src/
│   ├── index.js            # Public exports (CommonJS)
│   ├── agent.js            # Agent class
│   ├── tool.js             # tool() function — attaches ._toolDef to fn
│   ├── runtime.js          # AgentRuntime — serialize → POST /start → workers → result
│   ├── config.js           # AgentConfig — env var loading + defaults
│   ├── result.js           # makeAgentResult(), AgentHandle, AgentEvent types
│   ├── serializer.js       # Agent → AgentConfig JSON (mirrors Python AgentConfigSerializer)
│   └── worker-manager.js   # Wraps conductor-oss TaskManager for @tool workers
├── decorators/
│   ├── index.ts            # @AgentTool method decorator + toolsFrom() helper
│   └── tsconfig.json       # Separate TS config (experimentalDecorators: true)
├── types/
│   └── index.d.ts          # TypeScript type definitions for the JS API
├── examples/
│   ├── weather.js          # Plain JS weather example (primary demo)
│   └── weather-decorators.ts  # Same example with @AgentTool TS decorator
├── js-sdk-plan.md          # This file
├── package.json
└── .env.example
```

---

## Core APIs

### Tool definition — plain JavaScript (primary)

```js
const { tool } = require('@agentspan-ai/sdk')

const getWeather = tool(
  async function getWeather({ city }) {
    return { city, temperature_f: 72, condition: 'Sunny' }
  },
  {
    description: 'Get current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: { city: { type: 'string', description: 'City name' } },
      required: ['city'],
    },
  }
)
```

### Tool definition — TypeScript with `@AgentTool` decorator (optional)

> Note: JavaScript/TypeScript decorators only work on **class members**, not
> standalone functions. `tool()` is the equivalent for standalone functions.

```ts
import { AgentTool, toolsFrom } from '@agentspan-ai/sdk/decorators'

class WeatherTools {
  @AgentTool({
    description: 'Get current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: { city: { type: 'string' } },
      required: ['city'],
    },
  })
  async getWeather({ city }: { city: string }) {
    return { city, temperature_f: 72, condition: 'Sunny' }
  }
}

// toolsFrom() extracts decorated methods as tool-wrapped functions
const tools = toolsFrom(new WeatherTools())
```

### Agent

```js
const { Agent } = require('@agentspan-ai/sdk')

const agent = new Agent({
  name: 'weather_agent',
  model: 'openai/gpt-4o',           // "provider/model" format
  instructions: 'You are a helpful weather assistant.',
  tools: [getWeather],               // tool() functions or toolsFrom() output
  // Optional:
  // maxTurns: 25,
  // temperature: 0,
  // strategy: 'handoff',            // for multi-agent
  // agents: [subAgent],
})
```

### Runtime

```js
const { AgentRuntime } = require('@agentspan-ai/sdk')

const runtime = new AgentRuntime({ serverUrl: 'http://localhost:6767' })

// Blocking run — awaits completion
const result = await runtime.run(agent, "What's the weather in SF?")
result.printResult()

// Fire-and-forget with handle
const handle = await runtime.start(agent, "Long task")
const status = await handle.getStatus()   // { isComplete, isRunning, isWaiting, ... }
const result2 = await handle.wait()        // poll until complete
await handle.approve()                     // HITL approval
await handle.reject("Too risky")           // HITL rejection

// Streaming events
for await (const event of runtime.stream(agent, "What's the weather?")) {
  if (event.type === 'tool_call')    console.log('calling:', event.toolName, event.args)
  if (event.type === 'tool_result') console.log('result:', event.result)
  if (event.type === 'done')        console.log('output:', event.output)
}

await runtime.shutdown()
```

---

## Execution Flow

```
runtime.run(agent, prompt)
  │
  ├─1─ AgentConfigSerializer.serialize(agent)
  │        Agent tree → AgentConfig JSON (name, model, tools[], agents[])
  │
  ├─2─ POST /api/agent/start  { agentConfig, prompt, sessionId, media }
  │        Server compiles → Conductor workflow
  │        Returns { executionId }
  │
  ├─3─ WorkerManager.registerAll(agent.tools)
  │        For each @tool with a JS func:
  │          - POST /api/metadata/taskdefs  (register task type)
  │          - Add to TaskManager workers list
  │          - TaskManager.startPolling()
  │                ↕
  │          Conductor polls ← worker executes JS fn → result
  │
  └─4─ Poll GET /api/agent/{executionId}/status (500ms interval)
           OR stream SSE  GET /api/agent/stream/{executionId}
           Until COMPLETED / FAILED / TERMINATED / TIMED_OUT
           → AgentResult
```

---

## Worker Architecture (conductor-oss SDK)

```
tool(fn, options)
    │
    └─ fn._toolDef = { name, description, inputSchema, toolType: 'worker', func: fn }

AgentRuntime._prepareWorkers(agent)
    │
    ├─ Collect all worker tools (toolType === 'worker' && func !== null)
    ├─ Register task definitions on Conductor (POST /api/metadata/taskdefs)
    └─ TaskManager (from @io-orkes/conductor-javascript)
         workers: [{ taskDefName, execute: async (task) => ... }]
         .startPolling()   → polls Conductor, dispatches to fn
         .stopPolling()    → shutdown
```

---

## Serialization Format (mirrors Python SDK)

```json
{
  "agentConfig": {
    "name": "weather_agent",
    "model": "openai/gpt-4o",
    "instructions": "You are a helpful weather assistant.",
    "maxTurns": 25,
    "tools": [
      {
        "name": "getWeather",
        "description": "Get current weather for a city.",
        "inputSchema": {
          "type": "object",
          "properties": { "city": { "type": "string" } },
          "required": ["city"]
        },
        "toolType": "worker"
      }
    ]
  },
  "prompt": "What's the weather in SF?",
  "sessionId": "",
  "media": []
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Conductor server URL |
| `AGENTSPAN_AUTH_KEY` | — | Auth key (Orkes Cloud) |
| `AGENTSPAN_AUTH_SECRET` | — | Auth secret (Orkes Cloud) |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | `100` | Worker poll interval (ms) |
| `AGENTSPAN_LOG_LEVEL` | `INFO` | Log level: DEBUG, INFO, WARN, ERROR |
| `AGENT_LLM_MODEL` | — | LLM model, e.g. `openai/gpt-4o` |

---

## Test Commands

```bash
cd js

# Install dependencies
npm install

# Copy and configure env
cp .env.example .env
# Edit .env: set AGENT_LLM_MODEL=openai/gpt-4o

# Run weather example (plain JS)
AGENTSPAN_SERVER_URL=http://localhost:6767 \
AGENT_LLM_MODEL=openai/gpt-4o \
node examples/weather.js

# Custom prompt
AGENTSPAN_SERVER_URL=http://localhost:6767 \
AGENT_LLM_MODEL=openai/gpt-4o \
node examples/weather.js "What's the weather in Tokyo and London?"

# Run streaming example
AGENTSPAN_SERVER_URL=http://localhost:6767 \
AGENT_LLM_MODEL=openai/gpt-4o \
node examples/weather-stream.js

# Run TypeScript decorator example (requires ts-node)
AGENTSPAN_SERVER_URL=http://localhost:6767 \
AGENT_LLM_MODEL=openai/gpt-4o \
npx ts-node --project decorators/tsconfig.json examples/weather-decorators.ts
```
