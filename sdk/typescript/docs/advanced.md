# Advanced

Runtime configuration, the control-plane and workflow clients, the deploy/serve/run/plan lifecycle, structured output, credentials, plans (PLAN_EXECUTE), and skills.

## Runtime configuration

`new AgentRuntime(options?)` takes `AgentConfigOptions`. Every field falls back to an env var, then a default. Options take precedence over env vars.

```ts
import { AgentRuntime } from '@conductor-oss/conductor-agent-sdk';

const runtime = new AgentRuntime({
  serverUrl: 'http://localhost:6767/api',   // AGENTSPAN_SERVER_URL
  authKey: '…',                             // AGENTSPAN_AUTH_KEY
  authSecret: '…',                          // AGENTSPAN_AUTH_SECRET
  apiKey: '…',                              // AGENTSPAN_API_KEY (pre-minted token)
  workerPollIntervalMs: 100,                // AGENTSPAN_WORKER_POLL_INTERVAL
  workerThreads: 1,                         // AGENTSPAN_WORKER_THREADS
  logLevel: 'INFO',                         // AGENTSPAN_LOG_LEVEL
  llmRetryCount: 3,                         // AGENTSPAN_LLM_RETRY_COUNT
});
```

Full `AgentConfigOptions`: `serverUrl`, `apiKey`, `authKey`, `authSecret`, `workerPollIntervalMs`, `workerThreads`, `autoStartWorkers`, `autoStartServer`, `daemonWorkers`, `streamingEnabled`, `credentialStrictMode`, `logLevel`, `llmRetryCount`. The server URL is normalized to end with `/api`.

There is also a module-level singleton API for convenience — `configure(options)`, `run`, `start`, `stream`, `deploy`, `plan`, `serve`, `shutdown` — that operate on a shared runtime:

```ts
import { configure, run, shutdown } from '@conductor-oss/conductor-agent-sdk';
configure({ serverUrl: 'http://localhost:6767/api' });
const result = await run(agent, 'hi');
await shutdown();
```

## deploy vs serve vs run vs plan

| Method | What it does | Local workers? |
|---|---|---|
| `runtime.run(agent, prompt, opts?)` | Compile + start + stream + return an `AgentResult`. | Yes — registers and polls local `tool()` workers for the run. |
| `runtime.start(agent, prompt, opts?)` | Same as `run` but returns an `AgentHandle` for async interaction (stream, approve, pause, ...). | Yes. |
| `runtime.stream(agent, prompt, opts?)` | `start` + return its `AgentStream`. | Yes. |
| `runtime.deploy(agent, { schedules? })` | Compile + register the workflow definition on the server. No execution, no workers. CI/CD step. Returns `DeploymentInfo`. | No. |
| `runtime.serve(...agents)` | Register local tool workers and poll forever (blocks until SIGINT/SIGTERM). Run this in a long-lived worker process. | Yes (and keeps them alive). |
| `runtime.plan(agent)` | Compile to a workflow definition and return it, without executing. | No. |
| `runtime.shutdown()` | Stop worker polling. | — |

The typical production split: `deploy` once in CI/CD, run a `serve` process for the tool workers, and trigger executions via the control plane (`runtime.client.run(...)`) or schedules.

```ts
// CI/CD
await runtime.deploy(myAgent);

// Long-lived worker process
await runtime.serve(myAgent);   // blocks

// Trigger (control plane, no local workers needed for LLM-only / remote-tool agents)
const result = await runtime.client.run(myAgent, 'do the thing');
```

## `AgentClient` — control plane

`runtime.client` is an [`AgentClient`](api-reference.md#agentclient): the control-plane client for the `/agent/*` HTTP surface. It mints the auth JWT (from `authKey`/`authSecret`) and sends it as `X-Authorization`.

**Control-plane only:** `AgentClient.run/start` compile + start an agent and poll, but do **not** register or poll local tool workers. Use it for LLM-only agents, agents whose tools are remote (HTTP/MCP), or pre-deployed workflows. For agents with local `tool()` functions, use `runtime.run()` instead.

```ts
const client = runtime.client;   // or: new AgentClient(options)

// Compile + start + poll to result
const result = await client.run(agent, 'summarize this', { timeoutSeconds: 120 });

// Start and interact via a ClientHandle
const handle = await client.start(agent, 'do work');
const status = await handle.getStatus();
const final  = await handle.wait();
await handle.approve();          // / reject(reason) / send(message) / respond(body)

// Compile + register one or more agents (no execution)
const infos = await client.deploy(agentA, agentB);   // DeploymentInfo[]

// Deploy + reconcile cron schedules in one call
import { Schedule } from '@conductor-oss/conductor-agent-sdk';
await client.schedule(agent, [new Schedule({ name: 'nightly', cron: '0 0 0 * * *' })]);
```

Low-level endpoints are available too: `startAgent`, `deployAgent`, `compile`, `status`, `respond`, `getExecution`, `stream`. The `client.schedules` accessor is a `ScheduleClient`; `client.workflows` is a `WorkflowClient` (below).

## `WorkflowClient` — execution reads

`runtime.workflows` (also `runtime.client.workflows`) is a read-only [`WorkflowClient`](api-reference.md#workflowclient) over the underlying Conductor workflow API.

```ts
const wf = await runtime.workflows.getWorkflow(executionId);          // full execution (with tasks)
const status = await runtime.workflows.getStatus(executionId);        // 'RUNNING' | 'COMPLETED' | ...
const usage  = await runtime.workflows.extractTokenUsage(executionId);// aggregated across sub-workflows
// usage -> { promptTokens, completionTokens, totalTokens } | null
```

`extractTokenUsage` walks the execution tree (recursing into `SUB_WORKFLOW` tasks) and sums token usage — useful for multi-agent runs where tokens are spread across sub-workflows. Note: `result.tokenUsage` is already populated for you on a normal `run()`; this is for inspecting an execution by id after the fact.

## Structured output

Set `outputType` to a JSON Schema object (or a Zod schema — it is converted to JSON Schema). The model returns data conforming to the schema; the structured object lands under `result.output.result`.

```ts
const ArticleAnalysis = {
  type: 'object',
  properties: {
    title:     { type: 'string' },
    category:  { type: 'string', enum: ['tech', 'business', 'science'] },
    sentiment: { type: 'string', enum: ['positive', 'neutral', 'negative'] },
    keyTopics: { type: 'array', items: { type: 'string' } },
  },
  required: ['title', 'category', 'sentiment', 'keyTopics'],
};

const analyzer = new Agent({
  name: 'analyzer',
  model: 'openai/gpt-4o',
  instructions: 'Analyze the article and return structured data.',
  outputType: ArticleAnalysis,
});

const result = await runtime.run(analyzer, 'Analyze: "Quantum Error Correction Hits 99.9% Fidelity"');
const structured = result.output['result'] as Record<string, unknown>;
console.log(structured.category, structured.sentiment);
```

## Credentials and secrets

Pass credential names with `credentials: [...]` at the agent level and/or per tool. Secrets are resolved from the server's secret store at execution time and injected as environment variables for the tool call. For HTTP/MCP tools, reference them inline in headers with `${NAME}` substitution.

```ts
import { Agent, tool, httpTool, getCredential } from '@conductor-oss/conductor-agent-sdk';

// A worker tool: the secret is injected into the worker's process.env for the call
const dbLookup = tool(
  async (args: { query: string }) => {
    const key = process.env.DB_API_KEY ?? '';
    return { ok: key !== '' };
  },
  {
    name: 'db_lookup',
    description: 'Look up data.',
    inputSchema: { type: 'object', properties: { query: { type: 'string' } }, required: ['query'] },
    credentials: ['DB_API_KEY'],
  },
);

// Or fetch a credential explicitly inside a tool
const analytics = tool(
  async (args: { topic: string }) => {
    const key = await getCredential('ANALYTICS_KEY');
    return { topic: args.topic, ok: !!key };
  },
  { name: 'analytics', description: 'Query analytics.', inputSchema: {
    type: 'object', properties: { topic: { type: 'string' } }, required: ['topic'],
  }, credentials: ['ANALYTICS_KEY'] },
);

// HTTP tool with ${CRED} header substitution
const searchApi = httpTool({
  name: 'search_api',
  description: 'Search.',
  url: 'https://api.example.com/search',
  headers: { Authorization: 'Bearer ${SEARCH_API_KEY}' },
  credentials: ['SEARCH_API_KEY'],
});

const agent = new Agent({
  name: 'credentialed_agent',
  model: 'anthropic/claude-sonnet-4-6',
  instructions: '…',
  tools: [dbLookup, analytics, searchApi],
  credentials: ['DB_API_KEY', 'ANALYTICS_KEY', 'SEARCH_API_KEY'],
});
```

You can also pass `credentials` at call time: `runtime.run(agent, prompt, { credentials: ['X'] })`. Set `AGENTSPAN_CREDENTIAL_STRICT_MODE=true` (or `credentialStrictMode: true`) to disable env-var fallback so a missing secret is a hard error.

## Plans / PLAN_EXECUTE

`strategy: 'plan_execute'` runs a planner sub-agent to produce a JSON plan, then executes it deterministically as a sub-workflow. You **must** provide a `planner` agent (and may provide a `fallback`):

```ts
const harness = new Agent({
  name: 'plan_harness',
  model: 'openai/gpt-4o',
  strategy: 'plan_execute',
  planner: plannerAgent,     // required — produces the JSON plan
  fallback: agenticAgent,    // optional — runs agentically if the plan can't compile/run
  tools: [/* tools the plan steps call */],
});
const result = await runtime.run(harness, 'Build a release report.');
```

You can also supply a **deterministic static plan** with the typed builders and pass it via `RunOptions.plan` — it wins over the planner's output (the planner still runs, but its output is discarded):

```ts
import { Plan, Step, Op, Generate, Ref } from '@conductor-oss/conductor-agent-sdk';

const plan = new Plan({
  steps: [
    new Step('fetch', { operations: [new Op('fetch_data', { args: { source: 'db' } })] }),
    new Step('summarize', {
      dependsOn: ['fetch'],
      operations: [new Op('summarize', {
        generate: new Generate({
          instructions: 'Summarize the fetched data.',
          outputSchema: '{"type":"object","properties":{"summary":{"type":"string"}}}',
          context: new Ref('fetch'),     // reference a prior step's output
        }),
      })],
    }),
  ],
});

const result = await runtime.run(harness, 'Run the pipeline.', { plan });
```

Builders: `Plan({ steps, validation?, onSuccess?, onFailure? })`, `Step(id, { operations?, dependsOn?, parallel? })`, `Op(tool, { args? | generate? })`, `Generate({ instructions, outputSchema, maxTokens?, context? })`, `Validation(tool, { args?, successCondition? })`, `Action(tool, { args? })`, `Ref(stepId)`, `Context({ text? | url?, headers?, required?, maxBytes? })`.

For planner reference docs, set `plannerContext: [...]` on the agent (strings or `Context` instances; URLs are fetched at runtime, no recompile).

## Skills

`skill(path, options?)` loads a `SKILL.md` skill directory as an `Agent`; `loadSkills(dir)` loads every skill subdirectory keyed by name. Skills are framework agents (`_framework: "skill"`) and run via the same `run()` path; they can be wrapped with `agentTool` and used inside other agents.

```ts
import { skill, loadSkills, agentTool, Agent } from '@conductor-oss/conductor-agent-sdk';

const reviewer = skill('./skills/code-review', { model: 'openai/gpt-4o' });
const all = loadSkills('./skills');          // Record<string, Agent>

const orchestrator = new Agent({
  name: 'lead',
  model: 'anthropic/claude-sonnet-4-6',
  instructions: 'Delegate reviews to the code-review skill.',
  tools: [agentTool(reviewer)],
});
```

## See also

- [api-reference.md](api-reference.md) — the full public surface.
- [writing-agents.md](writing-agents.md) — schedules, HITL, guardrails, callbacks.
