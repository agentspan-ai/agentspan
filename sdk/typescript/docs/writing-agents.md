# Writing Agents

Everything you author is an `Agent`. A simple LLM agent, a tool-using agent, and a multi-agent orchestration are all the same `Agent` class with different options. This page walks the authoring surface.

All snippets import from `@conductoross/conductor-ai-sdk` and assume a runtime:

```ts
import { Agent, AgentRuntime, tool } from '@conductoross/conductor-ai-sdk';
const runtime = new AgentRuntime();
```

## Defining an agent

```ts
const agent = new Agent({
  name: 'greeter',                 // required; must match /^[a-zA-Z][a-zA-Z0-9_-]*$/
  model: 'openai/gpt-4o-mini',     // provider/model string
  instructions: 'Keep answers short.',
  temperature: 0.7,
  maxTurns: 25,                    // default 25
  maxTokens: 2048,
  timeoutSeconds: 0,               // 0 = server default
});
```

There is also a functional form, `agent(fn, options)`, where `fn` is the dynamic-instructions callable (see below):

```ts
import { agent } from '@conductoross/conductor-ai-sdk';

const a = agent(() => 'You are a helpful assistant.', {
  name: 'helper',
  model: 'openai/gpt-4o-mini',
});
```

### Instructions

Instructions can be a plain string, a callable, or a server-managed prompt template.

```ts
// Static
new Agent({ name: 'a', model, instructions: 'You are concise.' });

// Dynamic (callable) — evaluated to a string when the agent is serialized
new Agent({ name: 'a', model, instructions: () => `Today is ${new Date().toDateString()}.` });

// Server-managed prompt template (referenced by name + version)
import { PromptTemplate } from '@conductoross/conductor-ai-sdk';
new Agent({
  name: 'a',
  model,
  instructions: new PromptTemplate('support_greeting', { brand: 'Acme' }, 1),
});
```

## Tools

### Local tools — `tool()`

`tool()` wraps an async function. Pass a Zod schema **or** a plain JSON Schema object for `inputSchema`. The function runs locally as a Conductor worker that the runtime polls; the runtime registers and polls it automatically on `run()` / `serve()`.

```ts
const getWeather = tool(
  async (args: { city: string }) => {
    return { city: args.city, tempC: 21, conditions: 'sunny' };
  },
  {
    name: 'get_weather',
    description: 'Get the current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: { city: { type: 'string', description: 'City name' } },
      required: ['city'],
    },
  },
);

const agent = new Agent({
  name: 'weather_agent',
  model: 'openai/gpt-4o-mini',
  instructions: 'Answer weather questions using the tool.',
  tools: [getWeather],
});
```

`tool()` options: `name`, `description`, `inputSchema`, `outputSchema?`, `approvalRequired?`, `timeoutSeconds?`, `external?`, `credentials?`, `guardrails?`, `maxCalls?`, `retryCount?`, `retryDelaySeconds?`, `retryPolicy?`.

The tool function receives an optional second argument, the [`ToolContext`](api-reference.md#toolcontext) (`sessionId`, `executionId`, `agentName`, `metadata`, `dependencies`, and a mutable `state`). See [Stateful agents](#stateful-agents).

### Tool discovery — `@Tool` / `toolsFrom`

Decorate methods on a class and extract them, bound to the instance:

```ts
import { Tool, toolsFrom } from '@conductoross/conductor-ai-sdk';

class MathTools {
  @Tool({ description: 'Add two numbers.', inputSchema: {
    type: 'object', properties: { a: { type: 'number' }, b: { type: 'number' } }, required: ['a', 'b'],
  }})
  async add(args: { a: number; b: number }) { return { sum: args.a + args.b }; }
}

const tools = toolsFrom(new MathTools());     // ToolFunction[]
new Agent({ name: 'calc', model, tools });
```

> `@Tool`/`@AgentDec` are TypeScript experimental decorators — set `"experimentalDecorators": true` in your `tsconfig.json`.

### Built-in tools

These return a `ToolDef` that runs server-side (no local worker). Add them to `tools: [...]`.

| Builder | Tool type | Purpose |
|---|---|---|
| `httpTool({ name, description, url, method?, headers?, inputSchema?, credentials? })` | `http` | Call an HTTP endpoint. |
| `mcpTool({ serverUrl, name?, description?, headers?, toolNames?, maxTools?, credentials? })` | `mcp` | Expose an MCP server's tools. |
| `apiTool({ url, name?, description?, headers?, toolNames?, maxTools?, credentials? })` | `api` | Expose an OpenAPI/API as tools. |
| `agentTool(agent, { name?, description?, retryCount?, retryDelaySeconds?, optional? })` | `agent_tool` | Call another `Agent` as a tool (sub-agent). |
| `humanTool({ name, description, inputSchema? })` | `human` | Pause for human input (HITL). |
| `imageTool({ name, description, llmProvider, model, style?, size? })` | `generate_image` | Generate images. |
| `audioTool({ name, description, llmProvider, model, voice?, speed?, format? })` | `generate_audio` | Text-to-speech. |
| `videoTool({ name, description, llmProvider, model, duration?, resolution?, fps?, ... })` | `generate_video` | Generate video. |
| `pdfTool({ name?, description?, pageSize?, theme?, fontSize? })` | `generate_pdf` | Render markdown to PDF. |
| `waitForMessageTool({ name, description, batchSize?, blocking? })` | `pull_workflow_messages` | Dequeue messages from the workflow message queue. |
| `searchTool({ name, description, vectorDb, index, embeddingModelProvider, embeddingModel, namespace?, maxResults? })` | `rag_search` | RAG vector search. |
| `indexTool({ name, description, vectorDb, index, embeddingModelProvider, embeddingModel, namespace?, chunkSize?, chunkOverlap? })` | `rag_index` | RAG index/ingest. |

```ts
import { httpTool, mcpTool } from '@conductoross/conductor-ai-sdk';

const agent = new Agent({
  name: 'researcher',
  model: 'openai/gpt-4o-mini',
  tools: [
    httpTool({
      name: 'get_user',
      description: 'Fetch a user by id.',
      url: 'https://api.example.com/users/{id}',
      method: 'GET',
    }),
    mcpTool({ serverUrl: 'https://mcp.example.com/sse', toolNames: ['search'] }),
  ],
});
```

#### `waitForMessageTool` — workflow message queue

`waitForMessageTool` lets a running agent dequeue messages pushed into its workflow message queue (Conductor `PULL_WORKFLOW_MESSAGES`). No worker is needed — the server handles it. In blocking mode (default) the task stays in progress until a message arrives.

```ts
import { waitForMessageTool } from '@conductoross/conductor-ai-sdk';

const agent = new Agent({
  name: 'inbox_agent',
  model: 'openai/gpt-4o-mini',
  instructions: 'When asked to wait, call wait_for_message and process what arrives.',
  tools: [waitForMessageTool({
    name: 'wait_for_message',
    description: 'Wait for the next inbound message.',
    batchSize: 1,       // up to 100; default 1
    blocking: true,     // default true
  })],
});
```

#### `agentTool` — agent as a tool

```ts
import { agentTool } from '@conductoross/conductor-ai-sdk';

const translator = new Agent({ name: 'translator', model, instructions: 'Translate to French.' });

const orchestrator = new Agent({
  name: 'orchestrator',
  model,
  instructions: 'Use the translator tool when asked to translate.',
  tools: [agentTool(translator, { description: 'Translate text to French.' })],
});
```

## Multi-agent strategies

Set `agents: [...]` and a `strategy`. Strategies: `'sequential'`, `'parallel'`, `'handoff'`, `'router'`, `'round_robin'`, `'random'`, `'swarm'`, `'manual'`, `'plan_execute'`.

```ts
// Sequential — agents run in order. .pipe() is sugar for strategy: 'sequential'.
const pipeline = writer.pipe(editor);
// equivalent to:
// new Agent({ name: 'writer_editor', agents: [writer, editor], strategy: 'sequential' });

// Parallel — agents run concurrently, results gathered
const team = new Agent({ name: 'research_team', agents: [webResearcher, dataAnalyst], strategy: 'parallel' });

// Handoff — the parent LLM delegates to sub-agents (they appear as callable tools)
const support = new Agent({
  name: 'support',
  model,
  instructions: 'Route to the right specialist.',
  agents: [billingAgent, technicalAgent, salesAgent],
  strategy: 'handoff',
});

// Router — a router agent (or function) picks the sub-agent
const routed = new Agent({
  name: 'router',
  agents: [a, b],
  strategy: 'router',
  router: routerAgent,   // an Agent or (…) => string returning a sub-agent name
});
```

`scatterGather({ name, workers, ... })` is a convenience builder that returns a coordinator agent which fans a problem out to worker agents in parallel and synthesizes the results:

```ts
import { scatterGather } from '@conductoross/conductor-ai-sdk';
const coordinator = scatterGather({ name: 'fanout', workers: [worker], retryCount: 2 });
```

## Handoffs

For `swarm`/`handoff` strategies you can declare explicit handoff transitions with `handoffs: [...]`. Each condition has a `target` (a sub-agent name).

```ts
import { OnTextMention, OnToolResult, OnCondition } from '@conductoross/conductor-ai-sdk';

const team = new Agent({
  name: 'coding_team',
  model,
  agents: [pythonExpert, jsExpert],
  strategy: 'swarm',
  handoffs: [
    // Hand off when the output mentions text (case-insensitive)
    new OnTextMention({ target: 'python_expert', text: 'Python' }),

    // Hand off when a specific tool returns (optionally only if result contains text)
    new OnToolResult({ target: 'escalation', toolName: 'detect_severity', resultContains: 'critical' }),

    // Hand off when a custom predicate returns true (runs as a worker task)
    new OnCondition({ target: 'fallback', condition: (ctx) => ctx.result.length > 1000 }),
  ],
});
```

You can also constrain which transitions are allowed with `allowedTransitions: { agentName: ['otherAgent', ...] }`.

## Guardrails

Guardrails validate input or output. Attach them at the agent level (`guardrails: [...]`) or per-tool (`tool(fn, { guardrails: [...] })`). Each has a `position` (`'input'` | `'output'`, default `'output'`) and an `onFail` policy (`'raise'` | `'retry'` | `'fix'` | `'human'`, default `'raise'`).

```ts
import { guardrail, RegexGuardrail, LLMGuardrail } from '@conductoross/conductor-ai-sdk';

// Regex (runs on the server, no worker)
const noSecrets = new RegexGuardrail({
  name: 'no_api_keys',
  patterns: ['sk-[A-Za-z0-9]{20,}'],
  mode: 'block',          // 'block' fails if any pattern matches; 'allow' fails if none match
  onFail: 'raise',
  message: 'Output contained a secret.',
});

// LLM (server-side LLM judge)
const policy = new LLMGuardrail({
  name: 'safety',
  model: 'openai/gpt-4o-mini',
  policy: 'Reject any content that gives medical dosage advice.',
  position: 'output',
  onFail: 'retry',
  maxRetries: 2,
});

// Custom (your function, runs locally as a worker)
const minLength = guardrail(
  (content: string) => ({ passed: content.length >= 10, message: 'Too short' }),
  { name: 'min_length', position: 'output', onFail: 'fix' },
);

const agent = new Agent({
  name: 'safe_agent',
  model,
  instructions: '…',
  guardrails: [noSecrets.toGuardrailDef?.() ?? noSecrets, policy.toGuardrailDef?.() ?? policy, minLength],
});
```

`RegexGuardrail` / `LLMGuardrail` are class instances; the serializer accepts the instance directly. There is also a `guardrail.external({ name, position?, onFail? })` form for guardrails handled by a remote worker, and a `@Guardrail` decorator with `guardrailsFrom(instance)`.

## Termination + TextGate

Termination conditions decide when a multi-turn / multi-agent loop should stop. Pass one to `termination:`. They compose with `.and()` / `.or()` (or the variadic `AndCondition` / `OrCondition`).

```ts
import { TextMention, MaxMessage, TokenUsageCondition, StopMessage } from '@conductoross/conductor-ai-sdk';

const agent = new Agent({
  name: 'debate',
  model,
  agents: [a, b],
  strategy: 'round_robin',
  termination: new TextMention('TERMINATE')               // stop when output mentions text
    .or(new MaxMessage(10))                                // …or after 10 messages
    .or(new TokenUsageCondition({ maxTotalTokens: 50000 })),
});
```

Available conditions: `TextMention(text, caseSensitive?)`, `StopMessage(stopMessage)`, `MaxMessage(maxMessages)`, `TokenUsageCondition({ maxTotalTokens?, maxPromptTokens?, maxCompletionTokens? })`, and the composites `AndCondition(...)` / `OrCondition(...)`.

`TextGate` and `gate()` gate transitions (e.g. on `gate:`):

```ts
import { TextGate } from '@conductoross/conductor-ai-sdk';
new Agent({ name: 'a', model, gate: new TextGate({ text: 'APPROVED', caseSensitive: false }) });
```

## Callbacks

Subclass `CallbackHandler` and override the lifecycle hooks you care about. Each hook runs as a server-registered worker.

```ts
import { CallbackHandler } from '@conductoross/conductor-ai-sdk';

class Logger extends CallbackHandler {
  async onAgentStart(agentName: string, prompt: string) { console.log('[start]', agentName, prompt); }
  async onToolStart(agentName: string, toolName: string, args: unknown) { console.log('[tool]', toolName, args); }
  async onAgentEnd(agentName: string, result: unknown) { console.log('[end]', agentName); }
}

const agent = new Agent({ name: 'a', model, instructions: '…', callbacks: [new Logger()] });
```

Hooks: `onAgentStart`, `onAgentEnd`, `onModelStart`, `onModelEnd`, `onToolStart`, `onToolEnd`.

## Streaming

`runtime.stream(agent, prompt)` returns an `AgentStream` you can `for await` over. Events have a `type` (`'thinking'`, `'tool_call'`, `'tool_result'`, `'waiting'`, `'handoff'`, `'message'`, `'done'`, ...). You can also `runtime.start(...)` and call `handle.stream()`.

```ts
const stream = await runtime.stream(agent, 'Plan a 3-day trip to Tokyo.');
for await (const event of stream) {
  if (event.type === 'thinking')      console.log('[thinking]', event.content);
  else if (event.type === 'tool_call')   console.log('[tool]', event.toolName, event.args);
  else if (event.type === 'tool_result') console.log('[result]', event.toolName, event.result);
  else if (event.type === 'done')         console.log('[done]', event.output);
}
const result = await stream.getResult();   // terminal AgentResult after the stream ends
```

## Human-in-the-loop (HITL)

A tool with `approvalRequired: true`, or a `humanTool`, pauses execution and emits a `waiting` event. Resolve it via the handle / stream: `approve(output?)`, `reject(reason?)`, `send(message)`, or `respond(body)`.

```ts
const deleteData = tool(
  async (args: { table: string }) => ({ deleted: args.table }),
  {
    name: 'delete_data',
    description: 'Delete a table. Destructive — requires approval.',
    inputSchema: { type: 'object', properties: { table: { type: 'string' } }, required: ['table'] },
    approvalRequired: true,
  },
);

const agent = new Agent({ name: 'ops', model, tools: [deleteData], instructions: '…' });

const handle = await runtime.start(agent, 'Delete the stale_cache table.');
for await (const event of handle.stream()) {
  if (event.type === 'waiting') {
    // The waiting event carries the pending tool batch on event.pendingTool,
    // or fetch the full status:
    const status = await handle.getStatus();
    console.log('Approval needed for:', status.pendingTool?.toolCalls);

    await handle.approve();            // approve, or:
    // await handle.reject('Not allowed');
    // await handle.respond({ approved: true, note: 'go ahead' });
  } else if (event.type === 'done') {
    console.log('done', event.output);
  }
}
```

One HUMAN task gates the whole batch of pending tool calls with a single `{ approved, reason }` verdict — iterate `pendingTool.toolCalls` to see every tool covered. The `pendingTool` is mirrored onto the `waiting` event so you can read it without a `getStatus()` round-trip.

`humanTool` works the same way but lets the LLM ask the human a structured question; the response schema is on `pendingTool.response_schema`.

## Schedules

Attach cron schedules to an agent at deploy time. Reconciliation is declarative: a list upserts those and prunes the rest; `[]` purges all; omitting `schedules` leaves them untouched.

```ts
import { Agent, AgentRuntime, Schedule, schedules } from '@conductoross/conductor-ai-sdk';

const digest = new Agent({ name: 'eng_digest', model, instructions: 'Write a digest.' });

await runtime.deploy(digest, {
  schedules: [
    new Schedule({
      name: 'weekday-9am',
      cron: '0 0 9 * * MON-FRI',
      timezone: 'America/Los_Angeles',
      input: { channel: '#eng' },
      description: 'Weekday morning digest',
    }),
  ],
});

// Inspect / control via the `schedules` namespace
const infos = await schedules.list({ agent: digest.name });
await schedules.pause(infos[0].name, { reason: 'cooldown' });
await schedules.resume(infos[0].name);
const execId = await schedules.runNow(infos[0].name);
const next = await schedules.previewNext('0 0 9 * * MON-FRI', { n: 5 });

await runtime.deploy(digest, { schedules: [] });   // purge all
```

Lifecycle calls (`get`/`pause`/`resume`/`delete`/`runNow`) key on the **wire name** (the prefixed `name` returned in `ScheduleInfo`), not the short name you supplied. The `AgentClient` also has `schedule(agent, schedules)` (see [advanced.md](advanced.md#agentclient--control-plane)).

## Agent-from-method (`@AgentDec` / `agentsFrom`)

Define agents as decorated methods on a class and extract them:

```ts
import { AgentDec, agentsFrom } from '@conductoross/conductor-ai-sdk';

class MyAgents {
  @AgentDec({ name: 'summarizer', model: 'openai/gpt-4o-mini', instructions: 'Summarize text.' })
  summarize() {}

  @AgentDec({ name: 'classifier', model: 'openai/gpt-4o-mini', instructions: 'Classify text.' })
  classify() {}
}

const [summarizer, classifier] = agentsFrom(new MyAgents());   // Agent[]
```

## Stateful agents

Set `stateful: true` on an agent (or `stateful: true` on a tool def) to isolate tool workers per execution via a unique domain UUID. Within a single run, tools share a mutable `context.state` object; mutations are captured and propagated between tool calls.

```ts
import type { ToolContext } from '@conductoross/conductor-ai-sdk';

const addItem = tool(
  async (args: { item: string }, ctx?: ToolContext) => {
    const items: string[] = (ctx?.state?.list as string[]) ?? [];
    items.push(args.item);
    if (ctx?.state) ctx.state.list = items;
    return { total: items.length };
  },
  { name: 'add_item', description: 'Add an item.', inputSchema: {
    type: 'object', properties: { item: { type: 'string' } }, required: ['item'],
  }},
);

const agent = new Agent({ name: 'list_agent', model, tools: [addItem], stateful: true });
```

## Next

- [framework-agents.md](framework-agents.md) — run OpenAI / ADK / LangChain / LangGraph / Vercel AI agents.
- [advanced.md](advanced.md) — deploy/serve, control plane, structured output, credentials, plans, skills.
- [api-reference.md](api-reference.md) — full public surface.
