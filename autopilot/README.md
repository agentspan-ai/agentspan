# Agentspan Claw

**Product title:** Agentspan Claw
**Code name:** `agentspan-autopilot`

An autonomous agent product layer built on [Agentspan](https://agentspan.dev). Describe tasks in natural language — Claw creates, deploys, schedules, and manages the agents that execute them.

## What It Does

You say: *"scan my emails every morning and send me a summary on WhatsApp"*

Claw:
1. Asks 1-2 clarifying questions (which email? what time?)
2. Expands your request into a full agent specification with smart defaults
3. Generates the agent definition + worker code
4. Validates everything through a guardrailed pipeline
5. Deploys and schedules the agent on your Agentspan server
6. The chat thread becomes your ongoing control plane

Each agent is stored locally as a thin folder (`agent.yaml` + worker code) while all execution state, history, and logs live on the Agentspan server.

## Architecture

```
User prompt
  -> Orchestrator asks 1-2 critical questions
  -> Expands prompt (smart defaults)
  -> Spec validation gate
  -> Generates agent definition + worker code
  -> Code validation gate
  -> Integration check (credentials, reachability)
  -> Deploy validation gate (dry-run compile)
  -> Deploy & schedule on server
```

Three layers:

1. **Claw Orchestrator** — an Agentspan agent that powers the chat interface
2. **Guardrailed Creation Pipeline** — validation gates at each step
3. **Task Agents** — the agents users asked for, running on the Agentspan server

## Quick Start

```bash
# Prerequisites
# - Agentspan server running (default: localhost:6767)
# - Python 3.10+
# - uv package manager

# Install
cd autopilot
uv sync

# Launch the TUI
uv run python -m autopilot

# Or run the deep researcher demo directly
uv run python agents/deep_researcher/run.py "What are the latest advances in quantum computing?"

# Interactive research mode
uv run python agents/deep_researcher/run_interactive.py
```

## Project Structure

```
autopilot/
├── src/autopilot/
│   ├── config.py              # ~/.agentspan/autopilot/config.yaml management
│   ├── loader.py              # agent.yaml + workers/*.py -> Agent object
│   ├── registry.py            # integration registry (builtin tool lookup)
│   ├── orchestrator/          # orchestrator agent + creation/management tools
│   │   ├── tools.py           # expand_prompt, generate_agent, deploy, signal, etc.
│   │   └── state.py           # agent name -> execution ID mapping
│   ├── integrations/          # 19 pre-built Tier 1 integrations
│   │   ├── local_fs/          # file read/write/search
│   │   ├── web_search/        # agentic search (DDG + Brave + fetch + extract)
│   │   ├── doc_reader/        # PDF/DOCX/HTML extraction (markitdown + langextract)
│   │   ├── github/            # issues, PRs, reviews, repos
│   │   ├── gmail/             # read, send, search emails
│   │   ├── outlook/           # Microsoft Graph email
│   │   ├── slack/             # messages, channels
│   │   ├── whatsapp/          # WhatsApp Business API
│   │   ├── imessage/          # macOS iMessage via osascript
│   │   ├── linear/            # issues, projects, cycles
│   │   ├── jira/              # JQL search, issues, comments
│   │   ├── notion/            # pages, databases
│   │   ├── hubspot/           # contacts, deals
│   │   ├── salesforce/        # SOQL, records
│   │   ├── google_analytics/  # reports, realtime
│   │   ├── google_calendar/   # events
│   │   ├── google_drive/      # files, search
│   │   └── s3/                # AWS S3 objects
│   ├── tui/                   # terminal user interface
│   │   ├── app.py             # prompt_toolkit TUI
│   │   ├── commands.py        # /signal, /change, /agents, etc.
│   │   ├── dashboard.py       # agent list + status view
│   │   ├── notifications.py   # notification tracking
│   │   └── events.py          # SSE event formatting
│   └── templates/             # agent.yaml scaffolds
├── agents/                    # example agents
│   └── deep_researcher/       # multi-agent research pipeline
├── tests/                     # e2e tests (no mocks)
└── pyproject.toml
```

## User Data

All user data lives under `~/.agentspan/autopilot/`:

```
~/.agentspan/autopilot/
├── config.yaml           # server URL, model, polling interval, last-seen timestamps
├── state.json            # agent name -> execution ID mapping
└── agents/
    └── email-summary/
        ├── agent.yaml        # agent definition
        ├── expanded_prompt.md # full expanded specification
        └── workers/
            └── gmail_reader.py
```

## TUI Commands

| Command | Description |
|---------|-------------|
| `<message>` | Chat with the orchestrator |
| `/agents` | List all agents with status |
| `/dashboard` | Toggle dashboard view |
| `/signal <agent> <msg>` | Send transient signal to running agent |
| `/change <agent> <instr>` | Permanently modify agent behavior |
| `/pause <agent>` | Pause a scheduled agent |
| `/resume <agent>` | Resume a paused agent |
| `/status [agent]` | Show agent or orchestrator status |
| `/notifications` | Show unread notifications |
| `/stop` | Gracefully stop |
| `/disconnect` | Exit without stopping (resume later with `--resume`) |
| `/help` | Show all commands |

## Integration Layer

Three-tier integration strategy:

1. **Tier 1: Pre-built** — 19 integrations ship out of the box
2. **Tier 2: MCP** — community extensible via `mcp_tool()`
3. **Tier 3: Agent-driven** — orchestrator generates custom workers when no integration exists

## Agent Lifecycle

| State | Description |
|-------|-------------|
| DRAFT | Created locally, not yet deployed |
| DEPLOYING | Compiling on server, guardrails running |
| ACTIVE | Running or waiting for next trigger |
| PAUSED | User-paused or auto-paused after errors |
| WAITING | Mid-execution, needs user input (HITL) |
| ERROR | Failed, auto-retries up to 3x then pauses |
| ARCHIVED | Deactivated, local files retained |

## Trigger Models

- **Cron** — server-side scheduled execution (`"0 8 * * *"`)
- **Event-driven** — webhook triggers (v2)
- **Daemon** — always-on with `wait_for_message` pattern

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Agentspan server URL |
| `AGENTSPAN_LLM_MODEL` | `openai/gpt-4o` | Default LLM model |
| `BRAVE_API_KEY` | (none) | Optional: Brave Search API key for enhanced web search |

Integration credentials are managed via `agentspan credentials set <NAME>`.

## Testing

```bash
cd autopilot

# Run all tests
uv run pytest tests/ -v

# Skip network-dependent tests
uv run pytest tests/ -v -m "not network"
```

All tests are real end-to-end — no mocks.

## Design Documents

- [Design Specification](../docs/design/specs/2026-04-12-agentspan-claw-design.md)
- [Foundation Implementation Plan](../docs/design/plans/2026-04-12-claw-foundation.md)
