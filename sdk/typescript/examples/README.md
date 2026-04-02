# Examples

Runnable examples demonstrating every feature of the Agentspan TypeScript SDK.

---

## Examples vs. Production

> **Every example uses `runtime.run()` for convenience. In production, you should not.**

Examples call `runtime.run()` so you can try them in a single command — no setup, no
separate processes. But `run()` blocks the caller until the agent finishes, which is fine
for demos but not how you deploy real agents.

### Production: Deploy → Serve → Run

In production, the three concerns are separated:

```
┌──────────────────────────────────────────────────────────────┐
│  1. DEPLOY (once, during CI/CD)                              │
│     Registers the agent definition with the Agentspan server │
│                                                              │
│     await runtime.deploy(agent);                             │
│     // or CLI: agentspan deploy --package my-agents          │
├──────────────────────────────────────────────────────────────┤
│  2. SERVE (long-running worker process)                      │
│     Listens for tool-call tasks and executes them            │
│                                                              │
│     await runtime.serve(agent);                              │
│     // typically run as a daemon or container                │
├──────────────────────────────────────────────────────────────┤
│  3. RUN (on-demand, from anywhere)                           │
│     Triggers an agent execution                              │
│                                                              │
│     agentspan run <agent-name> "prompt"                      │
│     // or SDK: await runtime.run("agent_name", "prompt");    │
│     // or REST API                                           │
└──────────────────────────────────────────────────────────────┘
```

Every example includes the deploy/serve pattern as commented code at the bottom of its
`main()` function — look for the `// Production pattern:` comment.

See [63-deploy.ts](63-deploy.ts), [63b-serve.ts](63b-serve.ts), and
[63c-run-by-name.ts](63c-run-by-name.ts) for a complete working example of this pattern.

---

## Getting Started

### 1. Install dependencies

The core examples (numbered files in this directory) need the `agentspan` SDK:

```bash
npm install agentspan
```

Framework-specific examples require additional packages. Install only what you need:

#### Google ADK examples (`adk/`)

```bash
cd adk && npm install
```

#### LangGraph examples (`langgraph/`)

```bash
cd langgraph && npm install
```

#### OpenAI Agents SDK examples (`openai/`)

```bash
cd openai && npm install
```

Requires `OPENAI_API_KEY` environment variable.

#### Vercel AI examples (`vercel-ai/`)

```bash
cd vercel-ai && npm install
```

### 2. Configure your environment

Export environment variables:

```bash
export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
# export AGENTSPAN_AUTH_KEY=<key>     # if authentication is enabled
# export AGENTSPAN_AUTH_SECRET=<secret>
```

#### 2.1. Choose a model

The `AGENTSPAN_LLM_MODEL` variable uses the `provider/model-name` format. Examples:

| Provider | Model string | API key env var |
|----------|-------------|-----------------|
| OpenAI | `openai/gpt-4o-mini` (default) | `OPENAI_API_KEY` |
| Anthropic | `anthropic/claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| Google Gemini | `google_gemini/gemini-2.0-flash` | `GOOGLE_GEMINI_API_KEY` |
| AWS Bedrock | `aws_bedrock/...` | AWS credentials |
| Azure OpenAI | `azure_openai/...` | Azure credentials |

### 3. Run an example

```bash
# Core SDK examples (via ts-node, tsx, or compile first)
npx tsx examples/01-basic-agent.ts
npx tsx examples/15-agent-discussion.ts

# Framework-specific examples
cd adk && npx tsx 01-basic-agent.ts
cd langgraph && npx tsx 01-hello-world.ts
cd openai && npx tsx 01-basic-agent.ts
```

---

## Basic Examples

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 01 | [Basic Agent](01-basic-agent.ts) | Simplest possible agent — single LLM, no tools |
| 02 | [Tools](02-tools.ts) | Multiple `tool()` functions, approval-required tools |

## Tool Calling

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 02a | [Simple Tools](02a-simple-tools.ts) | Two tools (weather, stocks) — LLM picks the right one |
| 02b | [Multi-Step Tools](02b-multi-step-tools.ts) | Chained tool calls: lookup → fetch → calculate → answer |
| 03 | [Structured Output](03-structured-output.ts) | Zod `outputType` for typed, validated responses |
| 04 | [HTTP & MCP Tools](04-http-and-mcp-tools.ts) | Server-side tools via `httpTool()` and `mcpTool()` — no workers needed |
| 04b | [MCP Weather](04-mcp-weather.ts) | Real-time weather via an MCP server |
| 14 | [Existing Workers](14-existing-workers.ts) | Use existing worker task functions directly as agent tools |
| 33 | [Single Turn Tool](33-single-turn-tool.ts) | Single-turn tool invocation with immediate response |
| 33 | [External Workers](33-external-workers.ts) | Reference workers in other services — no local code needed |

## Multi-Agent Orchestration

| # | Example | Pattern |
|---|---------|---------|
| 05 | [Handoffs](05-handoffs.ts) | LLM-driven delegation to sub-agents |
| 06 | [Sequential Pipeline](06-sequential-pipeline.ts) | Agents run in order, output chains forward |
| 07 | [Parallel Agents](07-parallel-agents.ts) | All agents run concurrently, results aggregated |
| 08 | [Router Agent](08-router-agent.ts) | Router selects which sub-agent runs |
| 13 | [Hierarchical Agents](13-hierarchical-agents.ts) | 3-level nested hierarchy: CEO → leads → specialists |
| 15 | [Agent Discussion](15-agent-discussion.ts) | Round-robin debate between agents, piped to a summarizer |
| 16 | [Random Strategy](16-random-strategy.ts) | Random agent selected each turn (brainstorming) |
| 17 | [Swarm Orchestration](17-swarm-orchestration.ts) | Automatic transitions via handoff conditions |
| 18 | [Manual Selection](18-manual-selection.ts) | Human picks which agent speaks each turn |
| 20 | [Constrained Transitions](20-constrained-transitions.ts) | Restrict which agents can follow which |
| 29 | [Agent Introductions](29-agent-introductions.ts) | Agents introduce themselves before a group discussion |
| 38 | [Tech Trends](38-tech-trends.ts) | Multi-agent research pipeline with live HTTP API tools |

## Human-in-the-Loop

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 09 | [Human-in-the-Loop](09-human-in-the-loop.ts) | Tool approval gate — approve or reject before execution |
| 09b | [HITL with Feedback](09b-hitl-with-feedback.ts) | Custom feedback via `respond()` — editorial review |
| 09c | [HITL with Streaming](09c-hitl-streaming.ts) | Real-time event stream with approval pauses |
| 09d | [Human Tool](09d-human-tool.ts) | Human-as-a-tool for interactive conversations |
| 27 | [User Proxy Agent](27-user-proxy-agent.ts) | Human stand-in agent for interactive conversations |

## Guardrails & Safety

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 10 | [Guardrails](10-guardrails.ts) | Output validation with guardrail functions |
| 21 | [Regex Guardrails](21-regex-guardrails.ts) | Pattern-based blocking (emails, SSNs) and allow-listing |
| 22 | [LLM Guardrails](22-llm-guardrails.ts) | AI-powered content safety evaluation via a judge LLM |
| 31 | [Tool Guardrails](31-tool-guardrails.ts) | Pre-execution validation on tool inputs |
| 32 | [Human Guardrail](32-human-guardrail.ts) | Pause agent for human review when output fails |
| 35 | [Standalone Guardrails](35-standalone-guardrails.ts) | Use guardrails as plain callables — no agent needed |
| 36 | [Simple Agent Guardrails](36-simple-agent-guardrails.ts) | Mixed regex + custom guardrails on agents |
| 37 | [Fix Guardrail](37-fix-guardrail.ts) | Auto-correct output instead of retrying |

## Execution Modes

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 11 | [Streaming](11-streaming.ts) | Real-time event stream with `runtime.stream()` |
| 12 | [Long-Running](12-long-running.ts) | Async polling with `runtime.start()` |

## Credentials

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 08 | [Credentials](08-credentials.ts) | Server-side credential injection |
| 16 | [Isolated Tool](16-credentials-isolated-tool.ts) | Credentials scoped to a single tool |
| 16b | [Non-Isolated](16b-credentials-non-isolated.ts) | Credentials shared across tools |
| 16e | [HTTP Tool](16e-credentials-http-tool.ts) | Credentials in HTTP tool headers |
| 16f | [MCP Tool](16f-credentials-mcp-tool.ts) | Credentials in MCP tool headers |

## Deployment

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 63 | [Deploy](63-deploy.ts) | Register agent with the server |
| 63b | [Serve](63b-serve.ts) | Start a long-running worker |
| 63c | [Run by Name](63c-run-by-name.ts) | Execute a pre-deployed agent |
| 63d | [Serve from Package](63d-serve-from-package.ts) | Serve agents from a package |
| 63e | [Run Monitoring](63e-run-monitoring.ts) | Monitor running executions |

## Framework Integrations

| Directory | Framework | Examples |
|-----------|-----------|----------|
| [adk/](adk/) | Google ADK | 35 examples — agents, tools, streaming, planners, security |
| [langgraph/](langgraph/) | LangGraph | 45 examples — state graphs, react agents, memory, RAG |
| [openai/](openai/) | OpenAI Agents SDK | 10 examples — agents, tools, handoffs, guardrails |
| [vercel-ai/](vercel-ai/) | Vercel AI SDK | 10 examples — agents, tools, streaming, HITL |
| [quickstart/](quickstart/) | Agentspan Quickstart | 5 examples — minimal getting-started guides |
