# Agentspan Claw — Design Specification

**Product title:** Agentspan Claw
**Code name:** `agentspan-autopilot`
**Date:** 2026-04-12
**Status:** Draft

## Overview

Agentspan Claw is an autonomous agent product built on top of the Agentspan platform. Users describe tasks in natural language — "scan my emails every morning and send me a summary on WhatsApp" — and Claw creates, deploys, schedules, and manages the agents that execute those tasks.

The product provides both a TUI (terminal) and browser-based chat interface. Each "task" the user creates becomes an Agentspan agent, stored locally with its definition and worker code while all execution state, history, and logs live on the Agentspan server.

### Design Principles

- **Lazy-human first.** Users give minimal prompts. The system does the thinking.
- **Lean on Agentspan.** Don't reinvent what the platform already provides — execution history, credentials, streaming, signals, durability, guardrails.
- **Thin local, heavy server.** Local folder holds agent definitions and worker code. Everything else is server-side.
- **Local UI, remote server.** UI always initiates communication. The server never pushes to the UI.

### Target Users

- **Technical users** — TUI-first, can write custom tools, comfortable with the CLI.
- **Non-technical users** — browser-based chat, no terminal knowledge required.

Both interfaces share the same backend (orchestrator agent + Agentspan server).

---

## Architecture

### Three Layers

**1. Claw Orchestrator Agent**

An Agentspan agent that powers the chat interface. It handles:

- Conversation with the user (intent gathering, clarifying questions)
- Prompt expansion (turning lazy prompts into full agent specs)
- Agent creation (generating agent definitions + worker code)
- Agent management via deterministic tools (schedule, signal, list, stop, monitor)

The orchestrator runs as a stateful, always-on daemon agent using the `wait_for_message` pattern (see `examples/82b_coding_agent_tui.py`). Both TUI and browser connect to the same orchestrator execution.

**2. Guardrailed Creation Pipeline**

Validation gates between each step of agent creation. These are **validation checks implemented as orchestrator tools** (not Agentspan `Guardrail` objects, which are LLM output validators). Each gate runs deterministic checks and returns pass/fail:

- **Spec validation gate** — validates the expanded agent spec is complete (has integrations, schedule, error handling)
- **Code validation gate** — validates generated worker code compiles, has correct signatures, handles errors
- **Integration validation gate** — validates required credentials exist and integrations are reachable
- **Deploy validation gate** — dry-run compilation via Agentspan SDK before actual deployment

On validation failure, the orchestrator receives the error and self-corrects (up to 3 retries) before surfacing to the user.

**3. Created Agents (Task Agents)**

Standard Agentspan agents that the user asked for. Each:

- Lives locally as a thin folder (agent definition + worker code)
- Executes on the Agentspan server (state, history, logs)
- Can be scheduled (cron), event-driven, or always-on
- Can receive signals mid-execution
- Reports back through the chat thread and notifications panel

### Pipeline Flow

```
User prompt
  → Orchestrator asks 1-2 critical questions
  → Orchestrator expands prompt (with smart defaults)
  → Spec validation gate
  → Orchestrator generates agent definition + worker code
  → Code validation gate
  → Integration check (credentials, reachability)
  → Deploy validation gate (dry-run compile)
  → Deploy & schedule on server
```

---

## Agent Creation Flow — Progressive Expansion

The system uses progressive prompt expansion: ask the essentials, smart-default the rest, let users drill in if they care.

### Step 1: User drops a lazy prompt

```
You: scan my emails every morning and send me a summary on whatsapp
```

### Step 2: Orchestrator asks 1-2 critical questions

Only questions where there is no reasonable default. Examples:

- "Which email? (Gmail, Outlook, or other?)"
- "What time should the summary arrive?"

### Step 3: Orchestrator generates expanded spec with smart defaults

```
Agent: email-morning-summary
Schedule: Daily at 7:45 AM (15min buffer for processing)
Integrations: Gmail API (read), WhatsApp Business API (send)
Behavior:
  - Fetch unread emails from last 24h
  - Categorize: urgent, actionable, FYI, newsletters
  - Summarize each category (max 2-3 lines per email)
  - Send via WhatsApp as a formatted message
  - Mark urgent items with priority flag
Error handling: Retry 3x, then notify via WhatsApp
Credentials needed: GMAIL_OAUTH, WHATSAPP_API_KEY

Want to tweak anything, or should I build it?
```

### Step 4: Build, validate, deploy, show

The orchestrator runs through the guardrailed pipeline automatically:
1. Generates agent definition + worker code
2. Runs all validation gates (spec, code, integrations, deployment)
3. If credentials are available, **deploys immediately** and shows the execution status
4. If credentials are missing, acquires them (OAuth browser flow / API key page) then deploys
5. Shows the user exactly what was built: name, schedule, integrations, credentials, execution ID
6. Offers to show the agent's output: *"The agent is running. Say 'show output' to see what it produces."*

The user never has to ask "did it work?" — the system shows them.

### Step 5: Chat becomes the control plane

The chat thread persists as the agent's interaction channel. The user can:

- View output ("show output", "what did it produce?")
- Monitor status ("how did this morning's summary go?")
- Modify behavior ("also include my calendar from now on")
- Pause/resume ("pause this until next week")
- Signal running agents ("skip newsletters this time")

---

## Source Code Layout

Source lives in a top-level `autopilot/` directory in the repo, alongside `cli/`, `sdk/`, `server/`, and `ui/`:

```
autopilot/
├── pyproject.toml             # uv project, depends on agentspan SDK
├── orchestrator/              # orchestrator agent definition + workers
│   ├── agent.yaml             # orchestrator agent definition
│   └── workers/
│       ├── prompt_expander.py
│       ├── agent_builder.py
│       ├── agent_deployer.py
│       └── agent_manager.py
├── integrations/              # pre-built Tier 1 integration tools
│   ├── __init__.py            # integration registry
│   ├── gmail/
│   │   ├── __init__.py
│   │   └── tools.py           # @tool decorated functions
│   ├── slack/
│   ├── github/
│   ├── whatsapp/
│   ├── imessage/
│   ├── outlook/
│   ├── linear/
│   ├── jira/
│   ├── notion/
│   ├── hubspot/
│   ├── salesforce/
│   ├── google_analytics/
│   ├── google_calendar/
│   ├── google_drive/
│   ├── s3/
│   ├── web_search/
│   ├── web_scraper/
│   ├── doc_reader/            # markitdown + langextract
│   └── local_fs/
├── tui/                       # prompt_toolkit TUI application
│   ├── __init__.py
│   ├── app.py                 # main TUI entrypoint
│   ├── chat.py                # chat view (orchestrator interaction)
│   ├── dashboard.py           # agent list + notifications view
│   └── commands.py            # /signal, /change, /dashboard, etc.
├── templates/                 # agent.yaml scaffolds, worker templates
│   ├── cron_agent.yaml
│   ├── daemon_agent.yaml
│   └── worker_template.py
├── loader.py                  # load agent.yaml + workers from disk → Agent object
├── config.py                  # ~/.agentspan/autopilot/config.yaml management
└── tests/
    ├── test_prompt_expander.py
    ├── test_agent_builder.py
    ├── test_loader.py
    └── test_integrations/
```

Imports from the SDK: `from agentspan.agents import Agent, AgentRuntime, tool, mcp_tool`. The `autopilot/` directory depends on the SDK but is not part of it.

---

## Local Folder Structure (User Data)

All Claw user data lives under `~/.agentspan/autopilot/`:

```
~/.agentspan/autopilot/
├── config.yaml                    # server URL, default model, polling interval, last-seen timestamps
├── orchestrator/
│   ├── agent.yaml                 # Claw orchestrator agent definition
│   └── workers/
│       ├── prompt_expander.py     # expand lazy prompt → full spec
│       ├── agent_builder.py       # generate agent.yaml + worker code
│       ├── agent_deployer.py      # compile + register + schedule on server
│       └── agent_manager.py       # list, stop, signal, reschedule (deterministic)
└── agents/
    ├── email-morning-summary/
    │   ├── agent.yaml             # agent definition (name, model, instructions, schedule, trigger)
    │   ├── expanded_prompt.md     # full expanded prompt (human-readable)
    │   └── workers/
    │       ├── gmail_reader.py    # custom tool: fetch + categorize emails
    │       └── whatsapp_sender.py # custom tool: format + send summary
    ├── tax-review/
    │   ├── agent.yaml
    │   ├── expanded_prompt.md
    │   └── workers/
    │       └── pdf_analyzer.py
    └── docs-reviewer/
        ├── agent.yaml
        ├── expanded_prompt.md
        └── workers/
            └── folder_scanner.py
```

**What lives locally:** Agent definitions, expanded prompts, worker code.

**What lives on the server:** Execution state, history, logs, credentials, schedules. Accessed via Agentspan APIs.

---

## Dashboard & Notifications

Both TUI and browser provide:

### Agent List

Shows all agents with their current status (active, paused, waiting, error), last run time, and quick actions.

### Notifications Panel

A feed of agent outputs the user may have missed. Each notification shows:

- Agent name and timestamp
- Output summary (e.g., "2 urgent emails flagged")
- Priority indicator (urgent, normal, info)
- Actions: open chat thread, mark read, signal agent, respond (for HITL pauses)

### Unread State

Tracked locally in `~/.agentspan/autopilot/config.yaml` as last-seen timestamps per agent. Not server-side — the UI compares last-seen against execution timestamps from the server.

---

## Polling Architecture

The UI runs locally; the server may be remote. All data flows are UI-initiated.

| Flow | Mechanism | Frequency |
|------|-----------|-----------|
| Dashboard status | `GET /api/agent/executions?status=RUNNING,PAUSED,COMPLETED&since={lastPoll}` | Every 30s |
| Active chat stream | `GET /api/agent/stream/{executionId}` (SSE, client-initiated) | While chat is open |
| Notification fetch | `GET /api/agent/executions?hasOutput=true&since={lastSeen}` | On dashboard load + 30s poll |
| Signal agent | `POST /api/agent/{executionId}/signal` | User-initiated |
| Approve/reject HITL | `POST /api/agent/{executionId}/approve` | User-initiated |
| Stop agent | `POST /api/agent/{executionId}/stop` | User-initiated |

---

## Agent Lifecycle

### States

| State | Description |
|-------|-------------|
| **DRAFT** | Created locally, not yet deployed. Missing credentials or user hasn't confirmed. |
| **DEPLOYING** | Compiling on server, registering workers, setting up schedule. Guardrails running. |
| **ACTIVE** | Deployed and running (or waiting for next trigger). Healthy. |
| **PAUSED** | User-paused or auto-paused after errors. Schedule suspended. Can resume. |
| **WAITING** | Mid-execution, needs user input (HITL). Shows in notifications. |
| **ERROR** | Execution failed. Auto-retries up to 3x, then pauses and notifies user. |
| **ARCHIVED** | User deactivated. Local folder retained. Server-side schedule removed. Can reactivate. |

### State Transitions

```
DRAFT → DEPLOYING → ACTIVE
DEPLOYING → ERROR (deployment failed)
ACTIVE → PAUSED (user-paused or auto-paused after errors)
PAUSED → ACTIVE (user resumes)
ACTIVE → WAITING (HITL pause mid-execution)
WAITING → ACTIVE (user responds/approves)
ACTIVE → ARCHIVED (user deactivates)
PAUSED → ARCHIVED (user deactivates)
ARCHIVED → DEPLOYING (user reactivates)
Any state → ERROR → auto-retry (up to 3x) → PAUSED (if retries exhausted)
```

---

## Trigger Models

Agents support three trigger models. The orchestrator selects the appropriate model during prompt expansion based on the task.

### Scheduled (Cron)

Server-side cron via Agentspan scheduling API. Agent starts fresh each trigger.

```yaml
trigger:
  type: cron
  schedule: "0 8 * * *"  # every day at 8am
```

Best for: daily summaries, periodic reviews, batch processing.

### Event-Driven

Server receives a webhook or event notification and starts agent execution with the event payload.

```yaml
trigger:
  type: webhook
  source: gmail_push_notification
```

Best for: react to new emails, file uploads, Slack messages.

### Always-On (Daemon)

Long-running agent using the `wait_for_message` pattern. Stays alive, polls data sources, acts when conditions are met.

```yaml
trigger:
  type: daemon
  poll_interval: 60s
```

Best for: monitoring, live dashboards, chat bots.

---

## Signals

Claw leverages Agentspan's existing signal infrastructure. No reinvention needed.

### Existing Agentspan Signal Support

- `runtime.signal(execution_id, message)` — injects text into `_signal_injection` workflow variable
- Server endpoint: `POST /agent/{executionId}/signal` with `{"message": "..."}`
- Signals persist across LLM iterations until overwritten or cleared with `signal(eid, "")`
- Injection is automatic — prepended as `[SIGNALS]...[/SIGNALS]` before the LLM prompt on every iteration
- No LLM involvement needed — signals work on all agents
- Single signal at a time (new overwrites old)

### What Claw Adds

**Persistent vs transient — explicit commands, not NLP guessing:**

- **Persistent change** — user says "change the agent to also include my calendar" or uses `/change <agent> <instruction>` in TUI. Orchestrator updates `expanded_prompt.md` + `agent.yaml`, redeploys. Takes effect next execution cycle.
- **Transient signal** — user says "signal it to skip newsletters this time" or uses `/signal <agent> <message>` in TUI. Orchestrator calls `runtime.signal()`. Affects current/next run only.

In the chat interface, the orchestrator uses context to distinguish (the user is talking to the orchestrator, which is an LLM — it can ask "should this be a permanent change or just for this run?" if ambiguous). In the TUI, `/change` and `/signal` are explicit commands.

**Named agent signals** — Claw resolves agent name → execution ID → calls `runtime.signal()`. User never needs to know execution IDs.

---

## Integration Layer

Three-tier integration strategy with automatic fallback.

### Tier 1: Pre-built Integrations

Ship with the product, packaged as Agentspan tools with OAuth/API key flows.

#### v1 Core Set

| Category | Integrations | Notes |
|----------|-------------|-------|
| **Email** | Gmail, Outlook (Microsoft Graph) | Read, search, send, label, archive |
| **Messaging** | Slack, WhatsApp Business API, iMessage | Slack for teams, WhatsApp/iMessage for personal notifications |
| **Project Management** | Linear, Jira, Notion | Linear + Jira cover dev teams; Notion for docs/wikis |
| **Developer** | GitHub | Issues, PRs, reviews, actions, releases |
| **Deep Research** | Web Search (Brave/Tavily), Web Scraper/Crawler, PDF/Doc Reader | See research tooling details below |
| **Marketing & CRM** | HubSpot, Salesforce, Google Analytics | CRM + marketing automation + traffic analytics |
| **Productivity** | Google Calendar, Google Drive, Local Filesystem | Calendar, cloud files, local files |
| **Cloud Storage** | AWS S3 | Read/write/list objects, presigned URLs — universal file store |

#### Research Tooling Details

**Web Search:** Brave Search API or Tavily as the primary search provider. Returns structured results with URLs and snippets.

**Web Scraper/Crawler:** Fetch URL content, extract clean text from HTML, follow links for multi-page crawling. Built on `httpx` + `readability-lxml` or `trafilatura` for content extraction. Supports JavaScript-rendered pages via headless browser fallback.

**PDF/Document Reader:** Leverages two complementary libraries:
- [markitdown](https://github.com/microsoft/markitdown) — Microsoft's tool for converting PDF, DOCX, XLSX, PPTX, HTML, images, and more to clean Markdown. Good for structured documents, tables, and mixed media.
- [langextract](https://github.com/google/langextract) — Google's extraction library for high-fidelity text extraction from PDFs with layout awareness. Better for complex layouts, multi-column documents, and academic papers.

The document reader tool tries `markitdown` first (faster, broader format support), falls back to `langextract` for PDFs where layout fidelity matters.

#### v2 Additions

| Category | Integrations |
|----------|-------------|
| Email | — |
| Messaging | Twilio (SMS/Voice), Telegram, Discord |
| Project Management | Asana, Trello |
| Developer | GitLab, Sentry, Datadog, PagerDuty, AWS (beyond S3), GCP |
| Research | arXiv, Wikipedia, Hacker News, Reddit |
| Marketing | X/Twitter, LinkedIn, Mailchimp/SendGrid, Google Ads |
| Productivity | Outlook Calendar, Dropbox, Google Sheets, Todoist |
| Data & Finance | PostgreSQL/MySQL, Stripe, Plaid, QuickBooks/Xero, Airtable |

### Tier 2: MCP-based

Community extensible via Agentspan's `mcp_tool()` support:

- User or orchestrator points to any MCP server URL
- Orchestrator discovers available tools via MCP protocol
- Tools are available to any agent

### Tier 3: Agent-driven (Self-healing Fallback)

When no pre-built or MCP integration exists:

- Orchestrator uses code execution to build a custom worker
- Worker is written using the target service's API documentation
- Generated worker goes into the agent's `workers/` folder
- Code guardrail validates before deployment
- Credentials go through Agentspan's credential store

### Resolution Order

During prompt expansion, when the orchestrator identifies needed integrations:

1. Check pre-built library → use if available
2. Check configured MCP servers → use if available
3. Fall back to code generation → build a custom worker

The user never has to think about which tier is being used.

---

## Orchestrator Toolset

The Claw orchestrator is an Agentspan agent with two categories of tools.

### Creation Tools (LLM-driven, guardrailed)

| Tool | Description |
|------|-------------|
| `expand_prompt(seed_prompt, clarifications)` | Generate full agent spec from lazy prompt + user answers |
| `generate_agent(spec)` | Produce `agent.yaml` + worker code from validated spec |
| `resolve_integrations(spec)` | Check pre-built → MCP → flag what needs code generation |
| `generate_worker(integration_name, api_docs)` | Build a custom worker when no pre-built/MCP exists |

### Management Tools (deterministic, no LLM)

| Tool | Description |
|------|-------------|
| `deploy_agent(agent_dir)` | Compile via SDK, register workers, set schedule on server |
| `list_agents()` | Read `~/.agentspan/autopilot/agents/` + poll server for live statuses |
| `signal_agent(agent_name, message)` | Resolve name → execution ID → `runtime.signal()` |
| `update_agent(agent_name, changes)` | Modify `agent.yaml` / `expanded_prompt.md`, redeploy |
| `pause_agent(agent_name)` / `resume_agent(agent_name)` | Schedule control |
| `archive_agent(agent_name)` | Remove schedule, keep local files |
| `get_agent_status(agent_name)` | Poll server for execution state + latest output |
| `get_notifications(since)` | Poll server for recent outputs across all agents |

### Credential Tools (deterministic)

| Tool | Description |
|------|-------------|
| `check_credentials(agent_name)` | Verify all required credentials exist on server |
| `acquire_credentials(credential_name)` | Automatically acquire a missing credential — opens browser for OAuth flows (Google, Microsoft), navigates to API key pages (GitHub, Linear, Slack), reads AWS credentials from `~/.aws/credentials`. The system does the work, not the user. |

#### Credential Acquisition Strategy

The system must be fully autopilot — when credentials are missing, it doesn't just print instructions. It **does the work**:

| Credential Type | Acquisition Method |
|----------------|-------------------|
| Google OAuth (Gmail, Calendar, Drive, Analytics) | Opens browser to Google OAuth consent screen, runs local HTTP callback server, exchanges auth code for token, stores automatically |
| Microsoft OAuth (Outlook) | Opens browser to Microsoft identity login, same local callback flow |
| API Keys (GitHub, Linear, Notion, Slack, Jira, HubSpot, Brave) | Opens browser directly to the service's token/API key creation page, prompts user to paste the key |
| AWS (S3) | Reads from `~/.aws/credentials` if available, otherwise guides through IAM console |
| WhatsApp | Opens Meta Business settings page for token setup |
| iMessage | No credentials needed (local macOS only) |

---

## Session Management

Each Claw interaction is a **session** — a persistent orchestrator workflow execution on the Agentspan server. Sessions maintain full conversation history, agent creation context, and state.

### Session Lifecycle

- **A session is a single orchestrator workflow execution.** It stays RUNNING as long as the user is interacting with it.
- **The workflow must NOT complete between turns.** The orchestrator must always call `wait_for_message` after `reply_to_user` to keep the DoWhile loop alive. If the LLM fails to call `wait_for_message` (producing a text response instead), the TUI must detect this and **send the response back as a message** to keep the loop alive, rather than letting the workflow complete.
- **Sessions are resumable.** A user can disconnect (`/disconnect`) and resume later (`--resume`). The workflow stays alive on the server during disconnection.
- **Multiple sessions can exist.** Each session has a unique execution ID. The user can list sessions and switch between them.

### Session Commands

| Command | Description |
|---------|-------------|
| `--resume` | Resume the most recent session |
| `--resume <session-id>` | Resume a specific session |
| `--new` | Force start a new session (don't resume existing) |
| `/sessions` | List all active sessions with creation time and last activity |
| `/switch <session-id>` | Switch to a different active session |

### Session Storage

Sessions are tracked in `~/.agentspan/autopilot/sessions.json`:

```json
{
  "current": "e6c2d0cf-11af-455b-8443-7e3f5ea193a8",
  "sessions": [
    {
      "execution_id": "e6c2d0cf-11af-455b-8443-7e3f5ea193a8",
      "created_at": "2026-04-12T18:27:18Z",
      "last_active": "2026-04-12T18:28:47Z",
      "status": "RUNNING"
    }
  ]
}
```

### Handling LLM Workflow Completion

When the orchestrator LLM produces a text response without calling `wait_for_message`, the workflow's DoWhile loop terminates (the server emits DONE). The TUI handles this by:

1. Detecting the DONE event
2. **Using `runtime.resume()` to re-attach to the execution** if it's still resumable
3. If the execution truly ended, starting a **new execution in the same session context** — passing the conversation summary as the initial prompt so the LLM has continuity
4. The user never sees "Resuming session..." — it's transparent

This ensures the session never dies from the user's perspective, even when the LLM misbehaves.

---

## UI Surfaces

### TUI (Terminal)

Built on `prompt_toolkit`, extending the pattern from `examples/82b_coding_agent_tui.py`:

- Split-pane: scrollable output on top, input prompt at bottom
- Chat with the orchestrator (create agents, ask questions, modify agents)
- Dashboard view: agent list + notifications (toggle with `/dashboard`)
- Signal commands: `/signal <agent-name> <message>` (transient), `/change <agent-name> <instruction>` (persistent)
- Session management: `--resume`, `--new`, `/sessions`, `/switch`
- Connects to orchestrator via `wait_for_message` + SSE streaming

### Browser

React-based UI (leveraging Agentspan's existing React UI infrastructure at `localhost:6767`):

- Chat interface (claude.ai / chatgpt.com style)
- Left sidebar: agent list with status indicators
- Top bar: notifications with unread count
- Click agent → opens chat thread for that agent
- Click notification → opens relevant agent chat + scrolls to context
- Polls server for updates (no WebSocket/server-push dependency)

Both interfaces connect to the same orchestrator execution. Starting a chat in TUI and switching to browser continues the same conversation.

---

## New Infrastructure Required

The following Agentspan platform extensions are needed for Claw and **do not exist today**:

### Scheduling API (Required for v1)

A server-side API to register and manage cron-triggered agent executions. Conductor supports cron-triggered workflows natively, but Agentspan has not exposed this via its API layer.

**Needed endpoints:**

| Endpoint | Description |
|----------|-------------|
| `POST /api/agent/schedule` | Register a cron schedule for an agent (workflow name + cron expression) |
| `GET /api/agent/schedule/{agentName}` | Get current schedule for an agent |
| `PUT /api/agent/schedule/{agentName}` | Update schedule (change cron, pause/resume) |
| `DELETE /api/agent/schedule/{agentName}` | Remove schedule |
| `GET /api/agent/schedules` | List all scheduled agents |

**Implementation:** Wrap Conductor's `WorkflowScheduler` or implement using a lightweight scheduler (Quartz is already in the Spring Boot classpath) that calls `runtime.start()` on each tick.

### Execution Query Enhancements (Required for v1)

The current `GET /api/agent/executions` endpoint needs additional query parameters for the dashboard and notifications:

- `?since={timestamp}` — executions started or completed after a timestamp
- `?agentName={name}` — filter by agent name
- `?status={status}` — filter by status (RUNNING, PAUSED, COMPLETED, FAILED)

### Webhook Trigger Endpoint (Deferred to v2)

A server-side endpoint to receive external webhooks and start agent executions with the event payload. This is a significant platform extension that warrants its own design document.

### Agent Deployment from Disk (Required for v1)

Today, `AgentRuntime.start()` takes a Python `Agent` object constructed in code. Claw needs to construct agents from YAML definitions + Python worker files on disk. This requires:

- A loader that reads `agent.yaml` and dynamically imports worker Python files
- Dependency resolution for worker code (what packages does it need?)
- Default execution environment: workers run locally with `uv` for dependency management. Docker isolation is available via Agentspan's `DockerCodeExecutor` for untrusted/generated code.

---

## Error Handling & Recovery

### Error Categories

| Category | Examples | Retry? | Escalation |
|----------|----------|--------|------------|
| **Transient** | API rate limit, network timeout, temporary auth failure | Yes (up to 3x with backoff) | Pause agent, notify user |
| **Credential** | Expired OAuth token, revoked API key | No | Pause agent, prompt user to refresh credential |
| **Code bug** | Worker throws unhandled exception, wrong API call | No | Pause agent, show error + worker code to user |
| **Partial failure** | Emails fetched but WhatsApp send failed | Retry failed step only | Notify user of partial result |
| **Deployment** | Compilation error, invalid agent definition | No | Stay in DRAFT, show validation errors |

### Cron Agent Error Behavior

When a cron-triggered agent is in ERROR or PAUSED state when the next cron tick fires:

- **Skip the tick.** Do not start a new execution while one is in error.
- Notify the user that a scheduled run was skipped.
- Once the user resolves the error and resumes, the next cron tick starts normally.

### Retry Policy

- **Max retries:** 3 per execution (configurable in `agent.yaml`)
- **Backoff:** Exponential (1s, 5s, 25s)
- **After retries exhausted:** Transition to PAUSED, send notification to user
- **Retry scope:** Only the failed step is retried, not the entire agent execution (leverages Conductor's task-level retry)

---

## Data Model

### Artifacts

| Artifact | Format | Location | Description |
|----------|--------|----------|-------------|
| **Seed prompt** | Natural language | Chat history (server) | User's original lazy prompt |
| **Expanded spec** | Structured text | `expanded_prompt.md` (local) | Human-readable full specification generated by orchestrator |
| **Agent definition** | YAML | `agent.yaml` (local) | Machine-readable agent config consumed by the deployer |
| **Worker code** | Python files | `workers/*.py` (local) | Tool implementations for the agent |

### `agent.yaml` Schema

```yaml
name: email-morning-summary
version: 1
model: openai/gpt-4o
instructions: |
  You are an email summarization agent...

trigger:
  type: cron                    # cron | webhook | daemon
  schedule: "45 7 * * *"       # cron expression (cron type only)
  # source: gmail_push          # webhook source (webhook type only)
  # poll_interval: 60s          # polling interval (daemon type only)

tools:
  - gmail_reader               # references workers/gmail_reader.py
  - whatsapp_sender            # references workers/whatsapp_sender.py

credentials:
  - GMAIL_OAUTH
  - WHATSAPP_API_KEY

integrations:
  - name: gmail
    tier: builtin              # builtin | mcp | generated
  - name: whatsapp
    tier: builtin

error_handling:
  max_retries: 3
  backoff: exponential
  on_failure: pause_and_notify

metadata:
  created_at: 2026-04-12T08:30:00Z
  created_by: orchestrator
  last_deployed: 2026-04-12T08:31:00Z
```

---

## Versioning & Updates

### Agent Updates

When the user modifies a running agent ("also include my calendar"):

1. Orchestrator updates `expanded_prompt.md` and `agent.yaml` locally
2. `agent.yaml` version field is incremented
3. For **cron agents**: next cron tick picks up the new version. No in-flight disruption.
4. For **daemon agents**: orchestrator sends a signal with the change for the current run, and the new definition takes effect on next restart.
5. For **webhook agents**: next webhook trigger picks up the new version.

No in-flight execution is interrupted. Changes take effect on the next execution cycle.

### Rollback

Local folder retains previous versions via git (the `~/.agentspan/autopilot/` directory is a git repo initialized on first run). Users can roll back with standard git commands.

---

## Scope: v1 vs v2

### v1 (Initial Release)

- TUI interface (built on prompt_toolkit, extending 82b pattern)
- Orchestrator agent with prompt expansion + agent creation
- Cron scheduling (server-side scheduling API)
- Daemon agents (wait_for_message pattern)
- Pre-built integrations (Tier 1): Gmail, Outlook, Slack, WhatsApp, iMessage, Linear, Jira, Notion, GitHub, Web Search, Web Scraper/Crawler, PDF/Doc Reader (markitdown + langextract), HubSpot, Salesforce, Google Analytics, Google Calendar, Google Drive, AWS S3, Local Filesystem
- MCP integrations (Tier 2)
- Validation gates in creation pipeline
- Dashboard with notifications (TUI)
- Signal support (leveraging existing Agentspan signals)
- Local agent storage at `~/.agentspan/autopilot/`

### v2 (Future)

- Browser UI (React, shared orchestrator)
- Event-driven webhook triggers (requires server-side webhook endpoint design)
- Agent-driven code generation for integrations (Tier 3)
- Additional integrations: Twilio, Telegram, Discord, GitLab, Sentry, Datadog, PagerDuty, Asana, Trello, arXiv, Wikipedia, HN, Reddit, X/Twitter, LinkedIn, Mailchimp/SendGrid, Google Ads, Outlook Calendar, Dropbox, Google Sheets, Todoist, PostgreSQL/MySQL, Stripe, Plaid, QuickBooks/Xero, Airtable
- Multi-client concurrency handling (TUI + browser simultaneously)
- Agent versioning UI and rollback commands

---

## What Agentspan Already Provides (Not Reinvented)

| Capability | Agentspan Feature |
|------------|-------------------|
| Execution history | `GET /api/agent/executions` — full audit log with task-level detail |
| Credential management | Server-side encrypted storage, scoped execution tokens, env injection |
| Streaming | SSE via `GET /api/agent/stream/{executionId}`, client-initiated |
| Signals | `POST /agent/{executionId}/signal`, `[SIGNALS]` injection |
| Durability | Conductor workflow engine — survives process crashes |
| HITL | `approval_required` pauses, `approve/reject/respond` endpoints |
| Guardrails | Native guardrail system with retry/raise/fix/escalate failure modes |
| Code execution | Local, Docker, Jupyter, Serverless executors |
| Multi-agent orchestration | 8 strategies (handoff, sequential, parallel, router, swarm, etc.) |
| MCP support | `mcp_tool()` for MCP server integration |
| Session management | Stateful agents with `wait_for_message` pattern |
| React UI | Existing execution DAG viewer at localhost:6767 |
