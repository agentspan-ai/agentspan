<p align="center">
  <img src="https://github.com/agentspan/agentspan/raw/main/assets/logo-light.png#gh-light-mode-only" alt="Agentspan" width="400">
  <img src="https://github.com/agentspan/agentspan/raw/main/assets/logo-dark.png#gh-dark-mode-only" alt="Agentspan" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@agentspan/agentspan"><img src="https://img.shields.io/npm/v/@agentspan/agentspan?color=blue" alt="npm"></a>
  <a href="https://github.com/agentspan/agentspan/stargazers"><img src="https://img.shields.io/github/stars/agentspan/agentspan?style=social" alt="Stars"></a>
  <a href="https://github.com/agentspan/agentspan/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <a href="https://discord.gg/agentspan"><img src="https://img.shields.io/discord/1234567890?label=Discord&logo=discord&color=5865F2" alt="Discord"></a>
</p>

<p align="center">
  <a href="https://github.com/agentspan/agentspan">Main Repo</a> &bull;
  <a href="https://docs.agentspan.dev">Docs</a> &bull;
  <a href="https://discord.gg/agentspan">Discord</a> &bull;
  <a href="../sdk/python/">Python SDK</a> &bull;
  <a href="../server/">Server</a>
</p>

---

# Agentspan CLI

Command-line interface for managing the Agentspan runtime — start servers, run agents, stream events, and approve human-in-the-loop tasks from the terminal.

## Install

### Homebrew (macOS / Linux)

```bash
brew install agentspan/agentspan/agentspan
```

### npm

```bash
npm install -g @agentspan/agentspan
```

### Shell script

```bash
curl -fsSL https://raw.githubusercontent.com/agentspan/agentspan/main/cli/install.sh | sh
```

### From source

```bash
cd cli
go build -o agentspan .
```

## Quickstart

```bash
# Check system dependencies
agentspan doctor

# Set your LLM provider API key
export OPENAI_API_KEY=sk-...

# Start the runtime server (downloads automatically on first run)
agentspan server start

# Create an agent config
agentspan agent init mybot

# Run an agent
agentspan agent run --config mybot.yaml "What is the weather in NYC?"
```

## Commands

### `agentspan server` — Server Management

```bash
# Start the server (downloads latest JAR if needed)
agentspan server start

# Start a specific version on a custom port
agentspan server start --version 0.1.0 --port 9090

# Start with a default model
agentspan server start --model openai/gpt-4o

# Use a locally built JAR
agentspan server start --local

# Stop the server
agentspan server stop

# View server logs
agentspan server logs

# Follow logs in real-time
agentspan server logs -f
```

The server JAR is downloaded from GitHub releases and cached in `~/.agentspan/server/`. On each `server start`, the CLI checks for updates and re-downloads if a newer version is available.

| Flag | Description | Default |
|------|-------------|---------|
| `--port, -p` | Server port | `6767` |
| `--model, -m` | Default LLM model | — |
| `--version` | Specific server version | latest |
| `--jar` | Path to local JAR file | — |
| `--local` | Use locally built JAR from `server/build/libs/` | `false` |

### `agentspan agent` — Agent Operations

```bash
# Create a new agent config file
agentspan agent init mybot
agentspan agent init mybot --model anthropic/claude-sonnet-4-20250514 --format json

# Run an agent and stream output
agentspan agent run --name mybot "Hello, what can you do?"
agentspan agent run --config mybot.yaml "Hello, what can you do?"
agentspan agent run --name mybot --no-stream "Fire and forget"

# Continue a conversation
agentspan agent run --name mybot --session sess-123 "Follow up question"

# List all registered agents
agentspan agent list

# Get agent definition as JSON
agentspan agent get mybot
agentspan agent get mybot --version 2

# Delete an agent
agentspan agent delete mybot
agentspan agent delete mybot --version 1

# Compile agent config to agent definition (inspect only)
agentspan agent compile mybot.yaml
```

### Execution Management

```bash
# Check execution status
agentspan agent status <execution-id>

# Search execution history
agentspan agent execution
agentspan agent execution --name mybot
agentspan agent execution --status COMPLETED --since 1h
agentspan agent execution --since 7d
agentspan agent execution --window now-30m

# Stream events from a running agent
agentspan agent stream <execution-id>

# Respond to human-in-the-loop tasks
agentspan agent respond <execution-id> --approve
agentspan agent respond <execution-id> --deny --reason "Amount too high"
```

### Time Filters

The `--since` and `--window` flags accept human-readable time specs:

| Format | Meaning |
|--------|---------|
| `30s` | 30 seconds |
| `5m` | 5 minutes |
| `1h` | 1 hour |
| `1d` | 1 day |
| `7d` | 7 days |
| `1mo` | 1 month (30 days) |
| `1y` | 1 year (365 days) |

### `agentspan doctor` — System Check

Verifies your environment is ready to run Agentspan:

- Java 21+ installed
- Python 3.9+ installed
- Configured AI provider API keys and available models
- Port availability
- Ollama connectivity (if configured)
- Disk space
- Server connectivity

```bash
agentspan doctor
```

### `agentspan configure` — Configuration

```bash
# Set server URL and auth credentials
agentspan configure --url http://myserver:6767
agentspan configure --auth-key KEY --auth-secret SECRET

# Override server URL for a single command
agentspan --server http://other:6767 agent list
```

### `agentspan update` — Self-Update

```bash
agentspan update
```

Downloads and replaces the CLI binary with the latest version.

## Configuration

Configuration is stored in `~/.agentspan/config.json`. Environment variables take precedence:

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENTSPAN_SERVER_URL` | Server URL | `http://localhost:6767` |
| `AGENTSPAN_AUTH_KEY` | Auth key | — |
| `AGENTSPAN_AUTH_SECRET` | Auth secret | — |

**Precedence:** CLI flags > env vars > config file > defaults

### File Locations

| Path | Purpose |
|------|---------|
| `~/.agentspan/config.json` | CLI configuration |
| `~/.agentspan/server/agentspan-runtime.jar` | Cached server JAR |
| `~/.agentspan/server/server.pid` | Running server process ID |
| `~/.agentspan/server/server.log` | Server output logs |

## Agent Config Format

YAML or JSON. Create one with `agentspan agent init`.

```yaml
name: my-agent
description: A helpful assistant
model: openai/gpt-4o
instructions: You are a helpful assistant.
maxTurns: 25
tools:
  - name: web_search
    type: worker
```

See [examples/](examples/) for more samples.

## Supported Platforms

| OS | Architecture |
|----|-------------|
| macOS | x86_64, ARM64 (Apple Silicon) |
| Linux | x86_64, ARM64 |
| Windows | x86_64, ARM64 |

## Development

### Build

```bash
cd cli
go build -o agentspan .
```

### Cross-platform build

```bash
cd cli
VERSION=0.1.0 ./build.sh
```

Produces binaries in `cli/dist/` for all 6 platform/arch combinations.

### Release

Push a tag matching `cli-v*` to trigger the release workflow:

```bash
git tag cli-v0.1.0
git push origin cli-v0.1.0
```

This builds all binaries, creates a GitHub release, publishes to npm, and updates the Homebrew tap.

## Community

- **[Discord](https://discord.gg/agentspan)** — Ask questions, share what you're building, get help
- **[GitHub Issues](https://github.com/agentspan/agentspan/issues)** — Bug reports and feature requests
- **[Contributing Guide](../CONTRIBUTING.md)** — How to contribute

If Agentspan is useful to you, help others find it:

- [Star the repo](https://github.com/agentspan/agentspan) — it helps more than you think
- [Share on LinkedIn](https://www.linkedin.com/sharing/share-offsite/?url=https://github.com/agentspan/agentspan) — tell your network
- [Share on X/Twitter](https://twitter.com/intent/tweet?text=Agentspan%20%E2%80%94%20AI%20agents%20that%20don%27t%20die%20when%20your%20process%20does.%20Durable%2C%20scalable%2C%20observable.&url=https://github.com/agentspan/agentspan) — spread the word

## License

[MIT](../LICENSE)
