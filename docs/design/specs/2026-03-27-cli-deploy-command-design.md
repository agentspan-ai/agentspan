# CLI Deploy Command Design

**Date:** 2026-03-27
**Status:** Draft

---

## 1. Overview

A top-level `agentspan deploy` CLI command that discovers agents from user code by shelling out to the language runtime's SDK, then deploys them to the AgentSpan server. This bridges the Go CLI with the Python/TypeScript SDKs' `deploy()` functionality.

### 1.1 Design Principles

| Principle | Decision |
|-----------|----------|
| Auto-detect, allow override | Language and package inferred from project, flags override |
| Two-step with skip | Discover → confirm → deploy; `--yes` skips confirmation for CI/CD |
| Shell out to SDK | CLI delegates discovery and deployment to the SDK via subprocess |
| Filter, don't specify | `--agents` filters discovered agents by name, doesn't accept paths or configs |
| Fail loud | Missing runtime, missing SDK, no agents found — all explicit errors with remediation hints |

### 1.2 Command Signature

```
agentspan deploy [--agents foo,bar] [--language python|typescript] [--package myapp] [--yes] [--json] [--server URL]
```

---

## 2. Flags

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--agents` | `-a` | `[]string` | all discovered | Comma-separated agent names to filter |
| `--language` | `-l` | `string` | auto-detect | Override language detection (`python` or `typescript`) |
| `--package` | `-p` | `string` | inferred | Override package/path to scan for agents |
| `--yes` | `-y` | `bool` | `false` | Skip confirmation prompt |
| `--json` | | `bool` | `false` | Output machine-readable JSON instead of table |
| `--server` | | `string` | inherited from root | AgentSpan server URL |

---

## 3. Execution Flow

### 3.1 Language Detection

Priority order:
1. `--language` flag (explicit override)
2. Marker file detection in current directory:
   - Python: `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`
   - TypeScript: `package.json` with `typescript` or `ts-node` dependency, `tsconfig.json`
3. If both detected: error, ask user to specify `--language`
4. If neither detected: error with hint to use `--language`

### 3.2 Runtime Detection

After language detection, verify the runtime is available:

**Python:**
- Check for `python3` then `python` on PATH
- Prefer `.venv/bin/python` or `venv/bin/python` if a virtual environment exists in the project directory
- Allow `PYTHON` env var to override the binary path

**TypeScript:**
- Check for `npx` on PATH (implies Node.js installed)

### 3.3 Package Inference

The `--package` flag has different semantics per language:
- **Python**: a dotted module name (e.g., `myapp`) passed to `discover_agents()`
- **TypeScript**: a directory path (e.g., `./src`) passed to `discoverAgents()`

Priority order:
1. `--package` flag (explicit override)
2. Auto-inference:
   - **Python**: Parse `pyproject.toml` for `[project] name` or `[tool.setuptools.packages.find]`, or `setup.py` for `name` argument
   - **TypeScript**: Use `./src` as default scan directory; if `package.json` has a `main` field, use its parent directory
3. If inference fails: error with hint to use `--package`

### 3.4 Discovery

Shell out to the SDK's discovery entry point:

**Python:**
```bash
python -m agentspan.cli.discover --package <dotted_module_name>
```

**TypeScript:**
```bash
npx tsx node_modules/agentspan/bin/discover.ts --path <directory>
```

Note: TS uses `--path` (directory path) while Python uses `--package` (module name) because `discoverAgents()` in TS takes a filesystem path and scans for `.ts/.js` files, while Python's `discover_agents()` imports a dotted module and walks submodules.

Both print JSON to stdout:
```json
[
  {"name": "researcher", "framework": "native"},
  {"name": "summarizer", "framework": "native"},
  {"name": "classifier", "framework": "langchain"}
]
```

Stderr is forwarded to the user for import errors, warnings, etc.

### 3.5 Filtering

If `--agents` is specified:
- Filter discovered agents to only those whose names match
- If any requested name is not found in discovered agents, error:
  ```
  Error: agent "foo" not found. Discovered agents: researcher, summarizer, classifier
  ```

### 3.6 Confirmation

Unless `--yes` is set, print discovered agents and prompt:

```
Discovered 3 agents in myapp:
  Name         Framework
  ──────────── ─────────
  researcher   native
  summarizer   native
  classifier   langchain

Deploy 3 agents to http://localhost:6767? [y/N]
```

Default is No. Only `y` or `Y` proceeds.

### 3.7 Deployment

Shell out to the SDK's deploy entry point, passing configuration via environment variables.

**Auth credential forwarding**: The Go CLI reads credentials from its config (env vars or `~/.agentspan/config.json`). It forwards them to the subprocess as environment variables:
- `AGENTSPAN_SERVER_URL` — server URL
- `AGENTSPAN_API_KEY` — JWT token (from `agentspan login`)
- `AGENTSPAN_AUTH_KEY` / `AGENTSPAN_AUTH_SECRET` — Conductor-style auth (if configured)

All three are passed; the SDK picks whichever is relevant.

**Python:**
```bash
AGENTSPAN_SERVER_URL=<url> AGENTSPAN_API_KEY=<token> \
  python -m agentspan.cli.deploy --package <package> --agents foo,bar
```

**TypeScript:**
```bash
AGENTSPAN_SERVER_URL=<url> AGENTSPAN_API_KEY=<token> \
  npx tsx node_modules/agentspan/bin/deploy.ts --path <directory> --agents foo,bar
```

Both print JSON results to stdout:
```json
[
  {"agent_name": "researcher", "registered_name": "workflow_researcher", "success": true, "error": null},
  {"agent_name": "summarizer", "registered_name": "workflow_summarizer", "success": true, "error": null},
  {"agent_name": "classifier", "registered_name": "workflow_classifier", "success": false, "error": "serialization failed: unsupported tool type"}
]
```

### 3.8 Output

**Success (all agents deployed):**
```
Deployed 3 agents:
  ✓ researcher  →  workflow_researcher
  ✓ summarizer  →  workflow_summarizer
  ✓ classifier  →  workflow_classifier

Run with: agentspan agent run --name <agent> "your prompt"
```

**Partial failure:**
```
Deployed 2/3 agents:
  ✓ researcher  →  workflow_researcher
  ✓ summarizer  →  workflow_summarizer
  ✗ classifier  →  serialization failed: unsupported tool type

Run with: agentspan agent run --name <agent> "your prompt"
```

Exit code 1 on any failure.

**No agents deployed:**
```
Failed to deploy all agents:
  ✗ researcher  →  connection refused
  ✗ summarizer  →  connection refused

Check server status with: agentspan doctor
```

Exit code 1.

**JSON output mode** (`--json`):
```json
{
  "discovered": [{"name": "researcher", "framework": "native"}, ...],
  "deployed": [{"agent_name": "researcher", "registered_name": "workflow_researcher", "success": true, "error": null}, ...],
  "summary": {"total": 3, "succeeded": 2, "failed": 1}
}
```

---

## 4. SDK Entry Points (New Modules)

### 4.1 Python

Two new modules under `src/agentspan/cli/` (new package — does not exist yet, must be created).

**`src/agentspan/cli/__init__.py`** — empty

**`src/agentspan/cli/__main__.py`** — not needed; each submodule is invoked directly

**`src/agentspan/cli/discover.py`** — `python -m agentspan.cli.discover`
```python
"""CLI entry point for agent discovery. Called by the Go CLI."""
import argparse
import json
import sys
from agentspan.agents import discover_agents
from agentspan.agents.frameworks.serializer import detect_framework

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    args = parser.parse_args()

    try:
        agents = discover_agents([args.package])
    except Exception as e:
        print(f"Discovery failed: {e}", file=sys.stderr)
        sys.exit(1)

    result = [
        {"name": a.name, "framework": detect_framework(a) or "native"}
        for a in agents
    ]
    json.dump(result, sys.stdout)

if __name__ == "__main__":
    main()
```

Note: `detect_framework()` returns `None` for native agents; the `or "native"` fallback normalizes this for JSON output.

**`src/agentspan/cli/deploy.py`** — `python -m agentspan.cli.deploy`
```python
"""CLI entry point for agent deployment. Called by the Go CLI."""
import argparse
import json
import sys
import traceback
from agentspan.agents import discover_agents, deploy

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--agents", required=False)  # comma-separated
    args = parser.parse_args()

    agents = discover_agents([args.package])
    if args.agents:
        names = set(args.agents.split(","))
        agents = [a for a in agents if a.name in names]

    results = []
    for agent in agents:
        try:
            infos = deploy(agent)
            info = infos[0]
            results.append({
                "agent_name": info.agent_name,
                "registered_name": info.registered_name,
                "success": True,
                "error": None,
            })
        except Exception as e:
            results.append({
                "agent_name": agent.name,
                "registered_name": None,
                "success": False,
                "error": str(e),
            })
            print(f"Deploy failed for {agent.name}: {e}", file=sys.stderr)

    json.dump(results, sys.stdout)

if __name__ == "__main__":
    main()
```

Key difference from the discovery phase: deployment calls `deploy()` **per agent** with individual try/except, so a single agent failure doesn't crash the entire batch. The Go CLI always receives parseable JSON on stdout.

### 4.2 TypeScript

Two new scripts under `bin/` (new directory — does not exist yet, must be created). These are invoked via `npx tsx` rather than registered as `package.json` `bin` entries, since they are internal to the CLI integration and not user-facing commands.

**`bin/discover.ts`**
```typescript
import { discoverAgents } from '../src/discovery';
import { parseArgs } from 'node:util';

const { values } = parseArgs({
  options: { path: { type: 'string' } },
});

if (!values.path) {
  console.error('--path is required');
  process.exit(1);
}

const agents = await discoverAgents(values.path);
const result = agents.map(a => ({
  name: a.name,
  framework: 'native',  // TS SDK currently only discovers native Agent instances
}));

console.log(JSON.stringify(result));
```

**`bin/deploy.ts`**
```typescript
import { discoverAgents } from '../src/discovery';
import { getRuntime } from '../src/runtime';
import { parseArgs } from 'node:util';

const { values } = parseArgs({
  options: {
    path: { type: 'string' },
    agents: { type: 'string' },
  },
});

if (!values.path) {
  console.error('--path is required');
  process.exit(1);
}

let agents = await discoverAgents(values.path);
if (values.agents) {
  const names = new Set(values.agents.split(','));
  agents = agents.filter(a => names.has(a.name));
}

const runtime = getRuntime();
const results = [];

for (const agent of agents) {
  try {
    const info = await runtime.deploy(agent);  // single agent per call
    results.push({
      agent_name: info.agentName,
      registered_name: info.registeredName,
      success: true,
      error: null,
    });
  } catch (e: any) {
    results.push({
      agent_name: agent.name,
      registered_name: null,
      success: false,
      error: e.message || String(e),
    });
    console.error(`Deploy failed for ${agent.name}: ${e.message}`);
  }
}

console.log(JSON.stringify(results));
```

### 4.3 Known Limitations (TypeScript)

- **No framework agent discovery**: TS `discoverAgents()` only finds native `Agent` instances (`instanceof Agent` check). LangChain, OpenAI, or other framework agents in TS projects will not be discovered. This matches the current TS SDK capability and can be extended later.
- **No recursive discovery**: TS `discoverAgents()` scans only the top-level directory, not subdirectories. This should be improved in the TS SDK separately.

---

## 5. CLI Implementation (Go)

### 5.1 New Files

All new files live in `cmd/` to match the existing flat structure:

**`cmd/deploy.go`** — Cobra command definition, flag registration, orchestration logic (language detection, package inference, subprocess invocation, output formatting).

Helper functions for language detection, package inference, and subprocess execution are defined as unexported functions in this file. If the file grows too large during implementation, extract into `cmd/deploy_helpers.go` (same package).

### 5.2 Registration

```go
// cmd/deploy.go
func init() {
    rootCmd.AddCommand(deployCmd)  // top-level command
}
```

### 5.3 Subprocess Management

- Use `exec.CommandContext` with a 120-second timeout (hardcoded; can be made configurable later if needed)
- Pass server URL and all auth credentials via environment variables (not CLI args, to avoid leaking secrets in process lists)
- Capture stdout for JSON parsing, forward stderr to user's terminal
- If the subprocess exits non-zero and stdout contains valid JSON, treat it as partial failure results
- If the subprocess exits non-zero with no valid JSON on stdout, treat stderr as the error message
- For Python: detect runtime binary via venv check then `python3`/`python` on PATH
- For TypeScript: use `npx tsx` to run bin scripts directly from `node_modules/agentspan/`

---

## 6. Error Handling

| Scenario | Error Message | Exit Code |
|----------|---------------|-----------|
| No language detected | `Cannot detect project language. Use --language python\|typescript` | 1 |
| Both languages detected | `Found both Python and TypeScript projects. Use --language to specify` | 1 |
| Runtime not found | `Python not found. Install Python 3.10+ or use --language typescript` | 1 |
| SDK not installed | `agentspan package not found. Run: pip install agentspan` | 1 |
| Package inference failed | `Cannot determine package name. Use --package <name>` | 1 |
| No agents discovered | `No agents found in package 'myapp'. Define agents as module-level Agent instances` | 1 |
| Agent name not found | `Agent "foo" not found. Discovered agents: bar, baz` | 1 |
| User declines confirmation | (silent exit) | 0 |
| Subprocess timeout | `Deploy timed out after 120s` | 1 |
| All deploys fail | Error table + `Check server status with: agentspan doctor` | 1 |
| Partial failure | Mixed table (✓/✗) | 1 |
| All succeed | Success table + run hint | 0 |

---

## 7. Testing Strategy

### 7.1 Go CLI Tests

- **Unit tests** for language detection (mock filesystem with marker files)
- **Unit tests** for package inference (parse sample `pyproject.toml`, `package.json`)
- **Unit tests** for JSON result parsing (success, partial failure, malformed output)
- **Unit tests** for venv detection logic
- **Integration test** with mock subprocess that returns canned JSON

### 7.2 Python SDK Tests

- **Unit tests** for `agentspan.cli.discover` module (mock `discover_agents`)
- **Unit tests** for `agentspan.cli.deploy` module (mock `deploy`, including per-agent failure scenarios)
- **Integration test** with a sample package containing Agent instances

### 7.3 TypeScript SDK Tests

- Mirror Python test structure for TS entry points
- Test that `discoverAgents` → filter → deploy loop works with mock runtime

### 7.4 E2E Test

- Create a sample Python project with 2 agents
- Run `agentspan deploy --yes` against a test server
- Verify agents appear in `agentspan agent list`
- Run one of the deployed agents with `agentspan agent run --name <agent> "test"`
- Verify `--json` output is valid and parseable
- Verify `--agents` filtering works (deploy subset)
