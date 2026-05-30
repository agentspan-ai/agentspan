---
title: CLI Reference
description: Agentspan CLI commands for server, credentials, agents, skills, status, and execution history
---

# CLI Reference

**Python developers:** `pip install agentspan` gives you the SDK and the CLI. The pip package registers the `agentspan` command as a console script; on first invocation it downloads the Go binary from S3 and caches it.

**CLI only (no Python SDK):** `npm install -g @agentspan-ai/agentspan` — downloads the Go binary eagerly at install time. Useful if you don't have Python or want the binary pre-fetched.

```bash
agentspan version    # Print the CLI version
agentspan --help     # List all commands
```

## Server Commands

```bash
agentspan server start    # Download (if needed) and start the server
agentspan server stop     # Stop the server
agentspan server logs     # View server logs
```

`agentspan server start` downloads the Agentspan server JAR on first run (~50 MB) and starts it as a local process. The JAR is cached — subsequent starts are instant. The server runs on port `6767`. The UI and API are both served from the same port — open `http://localhost:6767` in your browser to see the visual execution UI.

## Diagnostics

```bash
agentspan doctor    # Check system dependencies and AI provider configuration
```

`agentspan doctor` verifies:
- CLI is installed and working
- Java runtime is available (required to run the server)
- Python SDK is installed
- API keys are configured
- Server is reachable

## Credential Management

Store secrets on the server once. Tools resolve them automatically at runtime — no `.env` files, no hardcoded keys, no secrets in git.

```bash
agentspan credentials set KEY value      # Store a credential (encrypted at rest)
agentspan credentials list               # List stored credential keys
agentspan credentials delete KEY         # Delete a credential
```

Credentials are encrypted with AES-256-GCM. Only the key names are shown in `list` — values are never exposed.

Example:

```bash
agentspan credentials set GITHUB_TOKEN ghp_xxxxxxxxxxxx
agentspan credentials set SEARCH_API_KEY xxx-your-key
```

Use them in tools with `@tool(credentials=["KEY"])`. See [Tools](/docs/concepts/tools) for details.

## Agent Commands

### Status

```bash
agentspan agent status <execution-id>    # Get detailed status of a running execution
```

### Respond to HITL

```bash
agentspan agent respond <execution-id> --approve
agentspan agent respond <execution-id> --deny --reason "Amount too large, escalate to finance"
agentspan agent respond <execution-id> --message "Please use a different approach"
```

### Execution History

```bash
agentspan agent execution --since 1h
agentspan agent execution --name my_agent --since 1d
agentspan agent execution --status COMPLETED --since 7d
agentspan agent execution --name my_agent --status FAILED --since 1mo
```

Time formats: `30s`, `5m`, `1h`, `6h`, `1d`, `7d`, `1mo`, `1y`

### Run and Stream

```bash
agentspan agent run --name my_agent "What is quantum computing?"    # Run deployed agent and stream output
agentspan agent run --config agent.yaml "What is quantum computing?" # Run from config file
agentspan agent stream <execution-id>                               # Stream events from a running execution
```

### List and Get

```bash
agentspan agent list                    # List all registered agents
agentspan agent get my_agent            # Get agent configuration JSON
agentspan agent compile my_agent        # Compile and inspect execution plan (dry run)
```

### Skills

```bash
agentspan skill run ./my-skill "Do the task" --model openai/gpt-4o
agentspan skill run my-skill "Do the task" --model openai/gpt-4o --version 2026.05.21
agentspan skill run code-review "Review current changes" --model openai/gpt-4o --workspace .
agentspan skill run code-review "Review docs too" --model openai/gpt-4o --filesystem docs=./docs
agentspan skill load ./my-skill --model openai/gpt-4o
agentspan skill register ./my-skill --model openai/gpt-4o --version 2026.05.21
agentspan skill list --all-versions
agentspan skill get my-skill --version 2026.05.21
agentspan skill pull my-skill ./my-skill-copy --version 2026.05.21
agentspan skill delete my-skill --version 2026.05.21 --yes
agentspan skill serve my-skill --version 2026.05.21 --script-timeout 300
```

When `skill run` or `skill serve` is given a registered skill name instead of
a local directory, the CLI downloads the package into
`~/.agentspan/skills/<name>/<version>/files` and reuses that cached copy until
the server checksum changes. Downloaded packages are checksum-verified before
the cache is installed or any script worker is started. If a registered skill
references another registered skill, the server resolves that reference at
compile time and the CLI downloads the referenced package too, so script tools
and `read_skill_file` work for both the parent and referenced skills. Referenced
skill versions are pinned when the parent is registered; running `parent@v1`
continues to use the child version that was latest at registration time.

`skill register` excludes generated directories, common secret files such as
`.env` and private keys, and paths matched by `.agentspanignore`.

`skill run` exposes the current directory as the `workspace` filesystem root by
default. Skills can list, read, search, and inspect git status/diff through
workspace tools served by the CLI. Use `--workspace <dir>` to point at a
different checkout, `--filesystem <name>=<path>` to expose additional read-only
roots, or `--no-workspace` to run without local filesystem context.

## Configuration

Configure the server URL and auth credentials:

```bash
agentspan configure --url https://your-server.example.com
agentspan configure --url https://your-server.example.com --auth-key my-key --auth-secret my-secret
```

Or set environment variables:

```bash
export AGENTSPAN_SERVER_URL=https://your-server.example.com
export AGENTSPAN_AUTH_KEY=your-key
export AGENTSPAN_AUTH_SECRET=your-secret
```

Or configure in Python code:

```python
from agentspan.agents import configure

configure(
    server_url="https://your-server.example.com",
    auth_key="your-key",
    auth_secret="your-secret",
)
```
