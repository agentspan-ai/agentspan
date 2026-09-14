# Agentspan Claw — Quick Start Guide

## Prerequisites

- **Agentspan server** running (default: `localhost:6767`)
- **Python 3.10+** with `uv` package manager
- At least one LLM API key configured (OpenAI, Anthropic, etc.)

## 1. Install

```bash
cd autopilot
uv sync
```

## 2. Configure

Set your LLM model and verify the server:

```bash
# Set your preferred model
export AGENTSPAN_LLM_MODEL=openai/gpt-4o

# Verify server is running
curl -s http://localhost:6767/api/agent/ && echo "Server OK"
```

Optional — enable live web search (otherwise uses DuckDuckGo):

```bash
export BRAVE_API_KEY=your-key-here
```

## 3. Try the Deep Researcher

The fastest way to see Claw in action:

```bash
# One-shot research report
uv run python agents/deep_researcher/run.py "What are the most promising approaches to fusion energy?"

# Interactive mode — submit multiple topics
uv run python agents/deep_researcher/run_interactive.py
```

This runs a 4-stage multi-agent pipeline:
1. **Research Planner** breaks the topic into sub-questions
2. **Web Researcher** searches the web for each question
3. **Analyst** synthesizes findings
4. **Report Writer** produces a structured report

## 4. Launch the TUI

```bash
uv run python -m autopilot
```

You'll see a split-pane terminal UI:
- **Top**: scrollable output
- **Bottom**: input prompt

Type a message to chat with the Claw orchestrator. It can:
- List available agents (`/agents`)
- Show agent details (`/status deep_researcher`)
- Create new agents from natural language descriptions
- Signal running agents (`/signal <agent> <message>`)
- Permanently modify agents (`/change <agent> <instruction>`)

Type `/help` for all commands.

## 5. Resume a Session

```bash
# Disconnect without stopping (agent keeps running)
# In TUI: /disconnect

# Resume later
uv run python -m autopilot --resume
```

## 6. Run a Specific Agent

```bash
# Run the deep researcher interactively via TUI
uv run python -m autopilot --agent deep_researcher
```

## 7. Set Up Integration Credentials

Agents that use external services need credentials:

```bash
# Gmail
agentspan credentials set GMAIL_ACCESS_TOKEN

# GitHub
agentspan credentials set GITHUB_TOKEN

# Slack
agentspan credentials set SLACK_BOT_TOKEN

# See which credentials an agent needs
# In TUI: /status <agent-name>
```

## 8. Create Your Own Agent

Ask the orchestrator in the TUI:

```
You: scan my gmail every morning at 8am and send me a summary on slack
```

The orchestrator will:
1. Ask which Gmail account and Slack channel
2. Generate a full agent spec
3. Create the agent files under `~/.agentspan/autopilot/agents/`
4. Validate and deploy

Or create manually:

```bash
mkdir -p ~/.agentspan/autopilot/agents/my-agent/workers

# Create agent definition
cat > ~/.agentspan/autopilot/agents/my-agent/agent.yaml << 'EOF'
name: my_agent
version: 1
model: openai/gpt-4o
instructions: |
  You are a helpful assistant that...

trigger:
  type: cron
  schedule: "0 8 * * *"

tools:
  - builtin:gmail
  - builtin:slack

credentials:
  - GMAIL_ACCESS_TOKEN
  - SLACK_BOT_TOKEN

error_handling:
  max_retries: 3
  backoff: exponential
  on_failure: pause_and_notify
EOF
```

## What's Next

- [Full README](README.md) — architecture, integrations, lifecycle
- [Design Spec](../docs/design/specs/2026-04-12-agentspan-claw-design.md) — the complete design document
- [TUI Commands](README.md#tui-commands) — all available commands
