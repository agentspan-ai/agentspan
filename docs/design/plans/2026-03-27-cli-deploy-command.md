# CLI Deploy Command Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a top-level `agentspan deploy` CLI command that discovers agents from user code via SDK subprocesses and deploys them to the server.

**Architecture:** The Go CLI shells out to Python/TypeScript SDK entry points for agent discovery and deployment. Two new Python modules (`agentspan.cli.discover`, `agentspan.cli.deploy`) and two new TypeScript bin scripts (`bin/discover.ts`, `bin/deploy.ts`) serve as the bridge. The Go command handles language detection, package inference, user confirmation, subprocess orchestration, and output formatting.

**Tech Stack:** Go (Cobra, fatih/color, text/tabwriter, os/exec), Python (argparse, agentspan SDK), TypeScript (node:util parseArgs, agentspan SDK)

**Spec:** `docs/superpowers/specs/2026-03-27-cli-deploy-command-design.md`

---

## Chunk 1: Python SDK Entry Points

### Task 1: Python Discovery Entry Point

**Files:**
- Create: `sdk/python/src/agentspan/cli/__init__.py`
- Create: `sdk/python/src/agentspan/cli/discover.py`
- Create: `sdk/python/tests/cli/__init__.py`
- Create: `sdk/python/tests/cli/test_discover.py`

- [ ] **Step 1: Create the cli package**

Create the empty `__init__.py`:

```python
# sdk/python/src/agentspan/cli/__init__.py
```

- [ ] **Step 2: Write the failing test for discover**

```python
# sdk/python/tests/cli/__init__.py
```

```python
# sdk/python/tests/cli/test_discover.py
import json
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest


def test_discover_outputs_json_with_agent_names():
    """discover should print JSON array of {name, framework} to stdout."""
    from agentspan.agents.agent import Agent

    mock_agent_1 = MagicMock(spec=Agent)
    mock_agent_1.name = "researcher"
    mock_agent_2 = MagicMock(spec=Agent)
    mock_agent_2.name = "summarizer"

    with patch("agentspan.cli.discover.discover_agents", return_value=[mock_agent_1, mock_agent_2]) as mock_discover, \
         patch("agentspan.cli.discover.detect_framework", return_value=None) as mock_detect:

        from agentspan.cli.discover import main
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sys.argv", ["discover", "--package", "myapp"]):
            main()

        result = json.loads(captured.getvalue())
        assert len(result) == 2
        assert result[0] == {"name": "researcher", "framework": "native"}
        assert result[1] == {"name": "summarizer", "framework": "native"}
        mock_discover.assert_called_once_with(["myapp"])


def test_discover_normalizes_none_framework_to_native():
    """detect_framework returns None for native agents; discover should output 'native'."""
    from agentspan.agents.agent import Agent

    mock_agent = MagicMock(spec=Agent)
    mock_agent.name = "bot"

    with patch("agentspan.cli.discover.discover_agents", return_value=[mock_agent]), \
         patch("agentspan.cli.discover.detect_framework", return_value=None):

        from agentspan.cli.discover import main
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sys.argv", ["discover", "--package", "pkg"]):
            main()

        result = json.loads(captured.getvalue())
        assert result[0]["framework"] == "native"


def test_discover_with_framework_agent():
    """Framework agents should have their framework string in output."""
    from agentspan.agents.agent import Agent

    mock_agent = MagicMock(spec=Agent)
    mock_agent.name = "lg_agent"

    with patch("agentspan.cli.discover.discover_agents", return_value=[mock_agent]), \
         patch("agentspan.cli.discover.detect_framework", return_value="langgraph"):

        from agentspan.cli.discover import main
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sys.argv", ["discover", "--package", "pkg"]):
            main()

        result = json.loads(captured.getvalue())
        assert result[0]["framework"] == "langgraph"


def test_discover_exits_1_on_import_error(capsys):
    """If discover_agents raises, exit with code 1 and print error to stderr."""
    with patch("agentspan.cli.discover.discover_agents", side_effect=ImportError("No module named 'badpkg'")):
        from agentspan.cli.discover import main
        with patch("sys.argv", ["discover", "--package", "badpkg"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd sdk/python && python -m pytest tests/cli/test_discover.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: Implement the discover module**

```python
# sdk/python/src/agentspan/cli/discover.py
"""CLI entry point for agent discovery. Called by the Go CLI.

Usage: python -m agentspan.cli.discover --package <dotted_module_name>

Prints JSON to stdout: [{"name": "...", "framework": "native"|"langgraph"|...}, ...]
"""
import argparse
import json
import sys

from agentspan.agents.runtime.discovery import discover_agents
from agentspan.agents.frameworks.serializer import detect_framework


def main():
    parser = argparse.ArgumentParser(description="Discover agents in a Python package")
    parser.add_argument("--package", required=True, help="Dotted Python package name to scan")
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

Also add `__main__.py` so `python -m agentspan.cli.discover` works:

```python
# sdk/python/src/agentspan/cli/discover/__init__.py
```

Wait — the module is a single file, not a package. For `python -m agentspan.cli.discover` to work with a single file, the `cli` directory must be a package and `discover.py` must be a module within it. Since `discover.py` is not a package itself, we need a workaround. The simplest approach: keep it as `agentspan/cli/discover.py` with the `if __name__ == "__main__"` block. Then invoke as `python -m agentspan.cli.discover`.

For this to work, Python needs `agentspan/cli/` to be a package (has `__init__.py`) and will look for `agentspan/cli/discover.py` as a module. When invoked with `-m agentspan.cli.discover`, Python runs the module's `__main__` block. This works as-is with the `if __name__ == "__main__": main()` pattern.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd sdk/python && python -m pytest tests/cli/test_discover.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/agentspan/cli/__init__.py sdk/python/src/agentspan/cli/discover.py sdk/python/tests/cli/__init__.py sdk/python/tests/cli/test_discover.py
git commit -m "feat(python-sdk): add CLI discovery entry point for agentspan deploy"
```

---

### Task 2: Python Deploy Entry Point

**Files:**
- Create: `sdk/python/src/agentspan/cli/deploy.py`
- Create: `sdk/python/tests/cli/test_deploy.py`

- [ ] **Step 1: Write the failing test**

```python
# sdk/python/tests/cli/test_deploy.py
import json
import io
from unittest.mock import patch, MagicMock

import pytest

from agentspan.agents.result import DeploymentInfo


def test_deploy_all_agents_success():
    """Deploy all discovered agents and return success JSON."""
    from agentspan.agents.agent import Agent

    mock_agent_1 = MagicMock(spec=Agent)
    mock_agent_1.name = "researcher"
    mock_agent_2 = MagicMock(spec=Agent)
    mock_agent_2.name = "summarizer"

    info1 = DeploymentInfo(registered_name="wf_researcher", agent_name="researcher")
    info2 = DeploymentInfo(registered_name="wf_summarizer", agent_name="summarizer")

    with patch("agentspan.cli.deploy.discover_agents", return_value=[mock_agent_1, mock_agent_2]), \
         patch("agentspan.cli.deploy.deploy", side_effect=[[info1], [info2]]):

        from agentspan.cli.deploy import main
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sys.argv", ["deploy", "--package", "myapp"]):
            main()

        result = json.loads(captured.getvalue())
        assert len(result) == 2
        assert result[0] == {"agent_name": "researcher", "registered_name": "wf_researcher", "success": True, "error": None}
        assert result[1] == {"agent_name": "summarizer", "registered_name": "wf_summarizer", "success": True, "error": None}


def test_deploy_filters_by_agent_names():
    """When --agents is provided, only deploy matching agents."""
    from agentspan.agents.agent import Agent

    mock_agent_1 = MagicMock(spec=Agent)
    mock_agent_1.name = "researcher"
    mock_agent_2 = MagicMock(spec=Agent)
    mock_agent_2.name = "summarizer"

    info1 = DeploymentInfo(registered_name="wf_researcher", agent_name="researcher")

    with patch("agentspan.cli.deploy.discover_agents", return_value=[mock_agent_1, mock_agent_2]) as mock_discover, \
         patch("agentspan.cli.deploy.deploy", side_effect=[[info1]]) as mock_deploy:

        from agentspan.cli.deploy import main
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sys.argv", ["deploy", "--package", "myapp", "--agents", "researcher"]):
            main()

        result = json.loads(captured.getvalue())
        assert len(result) == 1
        assert result[0]["agent_name"] == "researcher"
        # deploy should have been called with only one agent
        mock_deploy.assert_called_once()


def test_deploy_handles_per_agent_failure():
    """If one agent fails to deploy, it should appear as success=false, others still deploy."""
    from agentspan.agents.agent import Agent

    mock_agent_1 = MagicMock(spec=Agent)
    mock_agent_1.name = "good_agent"
    mock_agent_2 = MagicMock(spec=Agent)
    mock_agent_2.name = "bad_agent"

    info1 = DeploymentInfo(registered_name="wf_good", agent_name="good_agent")

    def deploy_side_effect(agent):
        if agent.name == "bad_agent":
            raise RuntimeError("serialization failed")
        return [info1]

    with patch("agentspan.cli.deploy.discover_agents", return_value=[mock_agent_1, mock_agent_2]), \
         patch("agentspan.cli.deploy.deploy", side_effect=deploy_side_effect):

        from agentspan.cli.deploy import main
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sys.argv", ["deploy", "--package", "myapp"]):
            main()

        result = json.loads(captured.getvalue())
        assert len(result) == 2
        good = next(r for r in result if r["agent_name"] == "good_agent")
        bad = next(r for r in result if r["agent_name"] == "bad_agent")
        assert good["success"] is True
        assert bad["success"] is False
        assert "serialization failed" in bad["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sdk/python && python -m pytest tests/cli/test_deploy.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement the deploy module**

```python
# sdk/python/src/agentspan/cli/deploy.py
"""CLI entry point for agent deployment. Called by the Go CLI.

Usage: python -m agentspan.cli.deploy --package <name> [--agents foo,bar]

Prints JSON to stdout: [{"agent_name": "...", "registered_name": "...", "success": true/false, "error": null/"..."}, ...]
"""
import argparse
import json
import sys

from agentspan.agents.runtime.discovery import discover_agents
from agentspan.agents import deploy


def main():
    parser = argparse.ArgumentParser(description="Deploy agents to AgentSpan server")
    parser.add_argument("--package", required=True, help="Dotted Python package name to scan")
    parser.add_argument("--agents", required=False, help="Comma-separated agent names to deploy")
    args = parser.parse_args()

    try:
        agents = discover_agents([args.package])
    except Exception as e:
        print(f"Discovery failed: {e}", file=sys.stderr)
        sys.exit(1)

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sdk/python && python -m pytest tests/cli/test_deploy.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/cli/deploy.py sdk/python/tests/cli/test_deploy.py
git commit -m "feat(python-sdk): add CLI deploy entry point for agentspan deploy"
```

---

## Chunk 2: TypeScript SDK Entry Points

### Task 3: TypeScript Discovery Bin Script

**Files:**
- Create: `sdk/typescript/bin/discover.ts`
- Create: `sdk/typescript/tests/bin/discover.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// sdk/typescript/tests/bin/discover.test.ts
import { describe, it, expect, vi } from 'vitest';
import { Agent } from '../../src/agent.js';

// We test the logic by extracting it into a testable function.
// The bin script will call this function.

describe('discover bin script', () => {
  it('should output JSON array of discovered agents', async () => {
    const mockAgent1 = new Agent({ name: 'researcher', model: 'openai/gpt-4o' });
    const mockAgent2 = new Agent({ name: 'summarizer', model: 'openai/gpt-4o' });

    const { formatDiscoveryResult } = await import('../../bin/discover.js');
    const result = formatDiscoveryResult([mockAgent1, mockAgent2]);

    expect(result).toEqual([
      { name: 'researcher', framework: 'native' },
      { name: 'summarizer', framework: 'native' },
    ]);
  });

  it('should return empty array when no agents found', async () => {
    const { formatDiscoveryResult } = await import('../../bin/discover.js');
    const result = formatDiscoveryResult([]);
    expect(result).toEqual([]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sdk/typescript && npx vitest run tests/bin/discover.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement the discover bin script**

```typescript
// sdk/typescript/bin/discover.ts
import { discoverAgents } from '../src/discovery.js';
import { parseArgs } from 'node:util';
import type { Agent } from '../src/agent.js';

export interface DiscoveryEntry {
  name: string;
  framework: string;
}

export function formatDiscoveryResult(agents: Agent[]): DiscoveryEntry[] {
  return agents.map(a => ({
    name: a.name,
    framework: 'native', // TS SDK currently only discovers native Agent instances
  }));
}

async function main() {
  const { values } = parseArgs({
    options: { path: { type: 'string' } },
    strict: false,
  });

  if (!values.path) {
    console.error('Error: --path is required');
    process.exit(1);
  }

  try {
    const agents = await discoverAgents(values.path as string);
    const result = formatDiscoveryResult(agents);
    console.log(JSON.stringify(result));
  } catch (e: any) {
    console.error(`Discovery failed: ${e.message || e}`);
    process.exit(1);
  }
}

// Only run main when executed directly (not imported for testing)
const isMain = process.argv[1]?.endsWith('discover.ts') || process.argv[1]?.endsWith('discover.js');
if (isMain) {
  main();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sdk/typescript && npx vitest run tests/bin/discover.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sdk/typescript/bin/discover.ts sdk/typescript/tests/bin/discover.test.ts
git commit -m "feat(typescript-sdk): add CLI discovery bin script for agentspan deploy"
```

---

### Task 4: TypeScript Deploy Bin Script

**Files:**
- Create: `sdk/typescript/bin/deploy.ts`
- Create: `sdk/typescript/tests/bin/deploy.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// sdk/typescript/tests/bin/deploy.test.ts
import { describe, it, expect, vi } from 'vitest';
import { Agent } from '../../src/agent.js';
import type { DeploymentInfo } from '../../src/types.js';

describe('deploy bin script', () => {
  it('should filter agents by name', async () => {
    const { filterAgents } = await import('../../bin/deploy.js');

    const agent1 = new Agent({ name: 'researcher', model: 'openai/gpt-4o' });
    const agent2 = new Agent({ name: 'summarizer', model: 'openai/gpt-4o' });

    const filtered = filterAgents([agent1, agent2], 'researcher');
    expect(filtered).toHaveLength(1);
    expect(filtered[0].name).toBe('researcher');
  });

  it('should return all agents when no filter specified', async () => {
    const { filterAgents } = await import('../../bin/deploy.js');

    const agent1 = new Agent({ name: 'researcher', model: 'openai/gpt-4o' });
    const agent2 = new Agent({ name: 'summarizer', model: 'openai/gpt-4o' });

    const filtered = filterAgents([agent1, agent2], undefined);
    expect(filtered).toHaveLength(2);
  });

  it('should format successful deployment result', async () => {
    const { formatDeployResult } = await import('../../bin/deploy.js');

    const info: DeploymentInfo = { registeredName: 'wf_researcher', agentName: 'researcher' };
    const result = formatDeployResult('researcher', info, null);

    expect(result).toEqual({
      agent_name: 'researcher',
      registered_name: 'wf_researcher',
      success: true,
      error: null,
    });
  });

  it('should format failed deployment result', async () => {
    const { formatDeployResult } = await import('../../bin/deploy.js');

    const result = formatDeployResult('bad_agent', null, 'connection refused');

    expect(result).toEqual({
      agent_name: 'bad_agent',
      registered_name: null,
      success: false,
      error: 'connection refused',
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sdk/typescript && npx vitest run tests/bin/deploy.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement the deploy bin script**

```typescript
// sdk/typescript/bin/deploy.ts
import { discoverAgents } from '../src/discovery.js';
import { deploy } from '../src/runtime.js';
import { parseArgs } from 'node:util';
import type { Agent } from '../src/agent.js';
import type { DeploymentInfo } from '../src/types.js';

export interface DeployResultEntry {
  agent_name: string;
  registered_name: string | null;
  success: boolean;
  error: string | null;
}

export function filterAgents(agents: Agent[], agentsFlag: string | undefined): Agent[] {
  if (!agentsFlag) return agents;
  const names = new Set(agentsFlag.split(','));
  return agents.filter(a => names.has(a.name));
}

export function formatDeployResult(
  agentName: string,
  info: DeploymentInfo | null,
  error: string | null,
): DeployResultEntry {
  if (info) {
    return {
      agent_name: agentName,
      registered_name: info.registeredName,
      success: true,
      error: null,
    };
  }
  return {
    agent_name: agentName,
    registered_name: null,
    success: false,
    error,
  };
}

async function main() {
  const { values } = parseArgs({
    options: {
      path: { type: 'string' },
      agents: { type: 'string' },
    },
    strict: false,
  });

  if (!values.path) {
    console.error('Error: --path is required');
    process.exit(1);
  }

  let agents: Agent[];
  try {
    agents = await discoverAgents(values.path as string);
  } catch (e: any) {
    console.error(`Discovery failed: ${e.message || e}`);
    process.exit(1);
  }

  agents = filterAgents(agents, values.agents as string | undefined);

  const results: DeployResultEntry[] = [];

  for (const agent of agents) {
    try {
      const info = await deploy(agent);  // uses exported singleton deploy()
      results.push(formatDeployResult(agent.name, info, null));
    } catch (e: any) {
      const errMsg = e.message || String(e);
      results.push(formatDeployResult(agent.name, null, errMsg));
      console.error(`Deploy failed for ${agent.name}: ${errMsg}`);
    }
  }

  console.log(JSON.stringify(results));
}

const isMain = process.argv[1]?.endsWith('deploy.ts') || process.argv[1]?.endsWith('deploy.js');
if (isMain) {
  main();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sdk/typescript && npx vitest run tests/bin/deploy.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sdk/typescript/bin/deploy.ts sdk/typescript/tests/bin/deploy.test.ts
git commit -m "feat(typescript-sdk): add CLI deploy bin script for agentspan deploy"
```

---

## Chunk 3: Go CLI — Language Detection & Package Inference

### Task 5: Language Detection

**Files:**
- Create: `cli/cmd/deploy.go`
- Create: `cli/cmd/deploy_test.go`

- [ ] **Step 1: Write the failing test for language detection**

```go
// cli/cmd/deploy_test.go
package cmd

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDetectLanguage_Python(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "pyproject.toml"), []byte("[project]\nname = \"myapp\""), 0644)

	lang, err := detectLanguage(dir, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "python" {
		t.Fatalf("expected python, got %s", lang)
	}
}

func TestDetectLanguage_TypeScript(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "tsconfig.json"), []byte("{}"), 0644)

	lang, err := detectLanguage(dir, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "typescript" {
		t.Fatalf("expected typescript, got %s", lang)
	}
}

func TestDetectLanguage_BothDetected_Error(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "pyproject.toml"), []byte(""), 0644)
	os.WriteFile(filepath.Join(dir, "tsconfig.json"), []byte(""), 0644)

	_, err := detectLanguage(dir, "")
	if err == nil {
		t.Fatal("expected error when both languages detected")
	}
}

func TestDetectLanguage_NeitherDetected_Error(t *testing.T) {
	dir := t.TempDir()

	_, err := detectLanguage(dir, "")
	if err == nil {
		t.Fatal("expected error when no language detected")
	}
}

func TestDetectLanguage_OverrideFlag(t *testing.T) {
	dir := t.TempDir()
	// No marker files, but flag overrides

	lang, err := detectLanguage(dir, "python")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "python" {
		t.Fatalf("expected python, got %s", lang)
	}
}

func TestDetectLanguage_SetupPy(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "setup.py"), []byte(""), 0644)

	lang, err := detectLanguage(dir, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "python" {
		t.Fatalf("expected python, got %s", lang)
	}
}

func TestDetectLanguage_PackageJsonWithTypescript(t *testing.T) {
	dir := t.TempDir()
	pkgJSON := `{"devDependencies": {"typescript": "^5.0.0"}}`
	os.WriteFile(filepath.Join(dir, "package.json"), []byte(pkgJSON), 0644)

	lang, err := detectLanguage(dir, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if lang != "typescript" {
		t.Fatalf("expected typescript, got %s", lang)
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cli && go test ./cmd/ -run TestDetectLanguage -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement language detection**

Add to `cli/cmd/deploy.go`:

```go
package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// detectLanguage determines the project language from marker files or flag override.
// Returns "python" or "typescript".
func detectLanguage(dir string, flagOverride string) (string, error) {
	if flagOverride != "" {
		switch flagOverride {
		case "python", "typescript":
			return flagOverride, nil
		default:
			return "", fmt.Errorf("unsupported language %q: use 'python' or 'typescript'", flagOverride)
		}
	}

	hasPython := fileExists(filepath.Join(dir, "pyproject.toml")) ||
		fileExists(filepath.Join(dir, "setup.py")) ||
		fileExists(filepath.Join(dir, "setup.cfg")) ||
		fileExists(filepath.Join(dir, "requirements.txt"))

	hasTypeScript := fileExists(filepath.Join(dir, "tsconfig.json")) ||
		packageJSONHasTypeScript(filepath.Join(dir, "package.json"))

	if hasPython && hasTypeScript {
		return "", fmt.Errorf("found both Python and TypeScript projects. Use --language to specify")
	}
	if !hasPython && !hasTypeScript {
		return "", fmt.Errorf("cannot detect project language. Use --language python|typescript")
	}
	if hasPython {
		return "python", nil
	}
	return "typescript", nil
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func packageJSONHasTypeScript(path string) bool {
	data, err := os.ReadFile(path)
	if err != nil {
		return false
	}
	var pkg map[string]interface{}
	if err := json.Unmarshal(data, &pkg); err != nil {
		return false
	}
	for _, depsKey := range []string{"dependencies", "devDependencies"} {
		if deps, ok := pkg[depsKey].(map[string]interface{}); ok {
			if _, ok := deps["typescript"]; ok {
				return true
			}
			if _, ok := deps["tsx"]; ok {
				return true
			}
			if _, ok := deps["ts-node"]; ok {
				return true
			}
		}
	}
	return false
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cli && go test ./cmd/ -run TestDetectLanguage -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add cli/cmd/deploy.go cli/cmd/deploy_test.go
git commit -m "feat(cli): add language detection for deploy command"
```

---

### Task 6: Package Inference

**Files:**
- Modify: `cli/cmd/deploy.go`
- Modify: `cli/cmd/deploy_test.go`

- [ ] **Step 1: Write the failing test for package inference**

Add to `cli/cmd/deploy_test.go`:

```go
func TestInferPackage_Python_Pyproject(t *testing.T) {
	dir := t.TempDir()
	toml := `[project]
name = "myapp"
`
	os.WriteFile(filepath.Join(dir, "pyproject.toml"), []byte(toml), 0644)

	pkg, err := inferPackage(dir, "python", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pkg != "myapp" {
		t.Fatalf("expected myapp, got %s", pkg)
	}
}

func TestInferPackage_Python_Pyproject_WithHyphens(t *testing.T) {
	dir := t.TempDir()
	toml := `[project]
name = "my-app"
`
	os.WriteFile(filepath.Join(dir, "pyproject.toml"), []byte(toml), 0644)

	pkg, err := inferPackage(dir, "python", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Python package names use underscores
	if pkg != "my_app" {
		t.Fatalf("expected my_app, got %s", pkg)
	}
}

func TestInferPackage_TypeScript_Default(t *testing.T) {
	dir := t.TempDir()
	os.MkdirAll(filepath.Join(dir, "src"), 0755)

	pkg, err := inferPackage(dir, "typescript", "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	expected := filepath.Join(dir, "src")
	if pkg != expected {
		t.Fatalf("expected %s, got %s", expected, pkg)
	}
}

func TestInferPackage_Override(t *testing.T) {
	dir := t.TempDir()

	pkg, err := inferPackage(dir, "python", "custom_pkg")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pkg != "custom_pkg" {
		t.Fatalf("expected custom_pkg, got %s", pkg)
	}
}

func TestInferPackage_Python_NoConfig_Error(t *testing.T) {
	dir := t.TempDir()

	_, err := inferPackage(dir, "python", "")
	if err == nil {
		t.Fatal("expected error when no config found")
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cli && go test ./cmd/ -run TestInferPackage -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement package inference**

Add to `cli/cmd/deploy.go`:

```go
import (
	"bufio"
	"strings"
)

// inferPackage determines the package name/path to scan for agents.
func inferPackage(dir string, language string, flagOverride string) (string, error) {
	if flagOverride != "" {
		return flagOverride, nil
	}

	switch language {
	case "python":
		return inferPythonPackage(dir)
	case "typescript":
		return inferTypeScriptPackage(dir)
	default:
		return "", fmt.Errorf("unsupported language: %s", language)
	}
}

func inferPythonPackage(dir string) (string, error) {
	// Try pyproject.toml first
	pyprojectPath := filepath.Join(dir, "pyproject.toml")
	if data, err := os.ReadFile(pyprojectPath); err == nil {
		if name := parsePyprojectName(string(data)); name != "" {
			// Convert hyphens to underscores (Python convention)
			return strings.ReplaceAll(name, "-", "_"), nil
		}
	}

	return "", fmt.Errorf("cannot determine package name. Use --package <name>")
}

// parsePyprojectName extracts the project name from pyproject.toml.
// Simple line-based parser — does not need a full TOML library.
func parsePyprojectName(content string) string {
	scanner := bufio.NewScanner(strings.NewReader(content))
	inProject := false
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "[project]" {
			inProject = true
			continue
		}
		if strings.HasPrefix(line, "[") && line != "[project]" {
			inProject = false
			continue
		}
		if inProject && strings.HasPrefix(line, "name") {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) == 2 {
				name := strings.TrimSpace(parts[1])
				name = strings.Trim(name, "\"'")
				return name
			}
		}
	}
	return ""
}

func inferTypeScriptPackage(dir string) (string, error) {
	// Default to ./src if it exists
	srcDir := filepath.Join(dir, "src")
	if info, err := os.Stat(srcDir); err == nil && info.IsDir() {
		return srcDir, nil
	}
	// Fall back to current directory
	return dir, nil
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cli && go test ./cmd/ -run TestInferPackage -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add cli/cmd/deploy.go cli/cmd/deploy_test.go
git commit -m "feat(cli): add package inference for deploy command"
```

---

### Task 7: Python Runtime Detection

**Files:**
- Modify: `cli/cmd/deploy.go`
- Modify: `cli/cmd/deploy_test.go`

- [ ] **Step 1: Write the failing test**

Add to `cli/cmd/deploy_test.go`:

```go
func TestFindPythonBinary_VenvExists(t *testing.T) {
	dir := t.TempDir()
	venvPython := filepath.Join(dir, ".venv", "bin", "python")
	os.MkdirAll(filepath.Dir(venvPython), 0755)
	os.WriteFile(venvPython, []byte("#!/bin/sh\n"), 0755)

	bin := findPythonBinary(dir)
	if bin != venvPython {
		t.Fatalf("expected venv python %s, got %s", venvPython, bin)
	}
}

func TestFindPythonBinary_NoVenv_FallsToPATH(t *testing.T) {
	dir := t.TempDir()
	// No .venv directory

	bin := findPythonBinary(dir)
	// Should return "python3" or "python" (whatever is on PATH)
	// We can't assert the exact value, but it shouldn't be empty on most systems
	if bin == "" {
		t.Skip("no python on PATH")
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cli && go test ./cmd/ -run TestFindPythonBinary -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement Python runtime detection**

Add to `cli/cmd/deploy.go`:

```go
import "os/exec"

// findPythonBinary returns the path to the best Python binary for the project.
// Checks: PYTHON env var > .venv/bin/python > venv/bin/python > python3 on PATH > python on PATH.
func findPythonBinary(dir string) string {
	// Environment variable override
	if envPython := os.Getenv("PYTHON"); envPython != "" {
		if _, err := exec.LookPath(envPython); err == nil {
			return envPython
		}
	}

	// Check for virtual environment
	for _, venvDir := range []string{".venv", "venv"} {
		venvPython := filepath.Join(dir, venvDir, "bin", "python")
		if _, err := os.Stat(venvPython); err == nil {
			return venvPython
		}
	}

	// Fall back to PATH
	for _, bin := range []string{"python3", "python"} {
		if path, err := exec.LookPath(bin); err == nil {
			return path
		}
	}

	return ""
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cli && go test ./cmd/ -run TestFindPythonBinary -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cli/cmd/deploy.go cli/cmd/deploy_test.go
git commit -m "feat(cli): add Python runtime detection with venv support"
```

---

## Chunk 4: Go CLI — Subprocess Runner & JSON Parsing

### Task 8: Subprocess Runner

**Files:**
- Modify: `cli/cmd/deploy.go`
- Modify: `cli/cmd/deploy_test.go`

- [ ] **Step 1: Write the failing test for subprocess JSON result parsing**

Add to `cli/cmd/deploy_test.go`:

```go
func TestParseDiscoveryResult(t *testing.T) {
	jsonStr := `[{"name":"researcher","framework":"native"},{"name":"bot","framework":"langgraph"}]`
	agents, err := parseDiscoveryResult([]byte(jsonStr))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(agents) != 2 {
		t.Fatalf("expected 2 agents, got %d", len(agents))
	}
	if agents[0].Name != "researcher" || agents[0].Framework != "native" {
		t.Fatalf("unexpected agent[0]: %+v", agents[0])
	}
	if agents[1].Name != "bot" || agents[1].Framework != "langgraph" {
		t.Fatalf("unexpected agent[1]: %+v", agents[1])
	}
}

func TestParseDiscoveryResult_Empty(t *testing.T) {
	agents, err := parseDiscoveryResult([]byte("[]"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(agents) != 0 {
		t.Fatalf("expected 0 agents, got %d", len(agents))
	}
}

func TestParseDiscoveryResult_InvalidJSON(t *testing.T) {
	_, err := parseDiscoveryResult([]byte("not json"))
	if err == nil {
		t.Fatal("expected error for invalid JSON")
	}
}

func TestParseDeployResult(t *testing.T) {
	jsonStr := `[
		{"agent_name":"a","registered_name":"wf_a","success":true,"error":null},
		{"agent_name":"b","registered_name":null,"success":false,"error":"failed"}
	]`
	results, err := parseDeployResult([]byte(jsonStr))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(results))
	}
	if !results[0].Success || results[0].AgentName != "a" {
		t.Fatalf("unexpected result[0]: %+v", results[0])
	}
	if results[1].Success || results[1].Error != "failed" {
		t.Fatalf("unexpected result[1]: %+v", results[1])
	}
}

func TestFilterDiscoveredAgents(t *testing.T) {
	agents := []discoveredAgent{
		{Name: "a", Framework: "native"},
		{Name: "b", Framework: "native"},
		{Name: "c", Framework: "langgraph"},
	}

	filtered, err := filterDiscoveredAgents(agents, []string{"a", "c"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(filtered) != 2 {
		t.Fatalf("expected 2, got %d", len(filtered))
	}
}

func TestFilterDiscoveredAgents_NotFound(t *testing.T) {
	agents := []discoveredAgent{
		{Name: "a", Framework: "native"},
	}

	_, err := filterDiscoveredAgents(agents, []string{"a", "missing"})
	if err == nil {
		t.Fatal("expected error for missing agent")
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cli && go test ./cmd/ -run "TestParse|TestFilter" -v`
Expected: FAIL (types/functions not defined)

- [ ] **Step 3: Implement types and parsing**

Add to `cli/cmd/deploy.go`:

```go
// Types for subprocess communication

type discoveredAgent struct {
	Name      string `json:"name"`
	Framework string `json:"framework"`
}

type deployResult struct {
	AgentName    string  `json:"agent_name"`
	RegisteredName *string `json:"registered_name"` // nullable
	Success      bool    `json:"success"`
	Error        string  `json:"error"`
}

func parseDiscoveryResult(data []byte) ([]discoveredAgent, error) {
	var agents []discoveredAgent
	if err := json.Unmarshal(data, &agents); err != nil {
		return nil, fmt.Errorf("failed to parse discovery output: %w", err)
	}
	return agents, nil
}

func parseDeployResult(data []byte) ([]deployResult, error) {
	var results []deployResult
	if err := json.Unmarshal(data, &results); err != nil {
		return nil, fmt.Errorf("failed to parse deploy output: %w", err)
	}
	return results, nil
}

func filterDiscoveredAgents(agents []discoveredAgent, names []string) ([]discoveredAgent, error) {
	if len(names) == 0 {
		return agents, nil
	}

	nameSet := make(map[string]bool)
	for _, n := range names {
		nameSet[n] = true
	}

	var filtered []discoveredAgent
	for _, a := range agents {
		if nameSet[a.Name] {
			filtered = append(filtered, a)
			delete(nameSet, a.Name)
		}
	}

	if len(nameSet) > 0 {
		var missing []string
		for n := range nameSet {
			missing = append(missing, n)
		}
		var available []string
		for _, a := range agents {
			available = append(available, a.Name)
		}
		return nil, fmt.Errorf("agent %q not found. Discovered agents: %s",
			missing[0], strings.Join(available, ", "))
	}

	return filtered, nil
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cli && go test ./cmd/ -run "TestParse|TestFilter" -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Implement subprocess execution functions**

Add to `cli/cmd/deploy.go`:

```go
import (
	"bytes"
	"context"
	"time"
)

// runSubprocess executes a command, captures stdout for JSON, forwards stderr.
func runSubprocess(ctx context.Context, env []string, name string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 120*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, name, args...)
	var stdout bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = os.Stderr // forward stderr to user
	cmd.Env = append(os.Environ(), env...)

	if err := cmd.Run(); err != nil {
		// If we have stdout data, return it (partial failure case)
		if stdout.Len() > 0 {
			return stdout.Bytes(), nil
		}
		if ctx.Err() == context.DeadlineExceeded {
			return nil, fmt.Errorf("command timed out after 120s")
		}
		return nil, fmt.Errorf("command failed: %w", err)
	}

	return stdout.Bytes(), nil
}

// buildEnv creates environment variables for the subprocess with auth credentials.
func buildEnv(cfg *config.Config) []string {
	var env []string
	env = append(env, "AGENTSPAN_SERVER_URL="+cfg.ServerURL)
	if cfg.APIKey != "" {
		env = append(env, "AGENTSPAN_API_KEY="+cfg.APIKey)
	}
	if cfg.AuthKey != "" {
		env = append(env, "AGENTSPAN_AUTH_KEY="+cfg.AuthKey)
	}
	if cfg.AuthSecret != "" {
		env = append(env, "AGENTSPAN_AUTH_SECRET="+cfg.AuthSecret)
	}
	return env
}

// execDiscover shells out to the SDK to discover agents.
func execDiscover(ctx context.Context, env []string, language, pythonBin, pkg string) ([]discoveredAgent, error) {
	var stdout []byte
	var err error

	switch language {
	case "python":
		stdout, err = runSubprocess(ctx, env, pythonBin, "-m", "agentspan.cli.discover", "--package", pkg)
	case "typescript":
		stdout, err = runSubprocess(ctx, env, "npx", "tsx", "node_modules/agentspan/bin/discover.ts", "--path", pkg)
	}
	if err != nil {
		return nil, err
	}

	return parseDiscoveryResult(stdout)
}

// execDeploy shells out to the SDK to deploy agents.
func execDeploy(ctx context.Context, env []string, language, pythonBin, pkg string, agentNames []string) ([]deployResult, error) {
	var stdout []byte
	var err error

	agentsFlag := strings.Join(agentNames, ",")

	switch language {
	case "python":
		args := []string{"-m", "agentspan.cli.deploy", "--package", pkg, "--agents", agentsFlag}
		stdout, err = runSubprocess(ctx, env, pythonBin, args...)
	case "typescript":
		args := []string{"tsx", "node_modules/agentspan/bin/deploy.ts", "--path", pkg, "--agents", agentsFlag}
		stdout, err = runSubprocess(ctx, env, "npx", args...)
	}
	if err != nil {
		return nil, err
	}

	return parseDeployResult(stdout)
}
```

- [ ] **Step 6: Commit**

```bash
git add cli/cmd/deploy.go cli/cmd/deploy_test.go
git commit -m "feat(cli): add subprocess runner and JSON parsing for deploy"
```

---

## Chunk 5: Go CLI — Cobra Command & Output Formatting

### Task 9: Deploy Command & Output

**Files:**
- Modify: `cli/cmd/deploy.go`
- Modify: `cli/cmd/deploy_test.go`

- [ ] **Step 1: Write the failing test for output formatting**

Add to `cli/cmd/deploy_test.go`:

```go
func TestFormatDeployOutput_AllSuccess(t *testing.T) {
	results := []deployResult{
		{AgentName: "a", WorkflowName: strPtr("wf_a"), Success: true},
		{AgentName: "b", WorkflowName: strPtr("wf_b"), Success: true},
	}
	output := formatDeployOutput(results)
	if !strings.Contains(output, "Deployed 2 agents") {
		t.Fatalf("expected success header, got:\n%s", output)
	}
	if !strings.Contains(output, "a") || !strings.Contains(output, "wf_a") {
		t.Fatalf("expected agent details, got:\n%s", output)
	}
	if !strings.Contains(output, "agentspan agent run") {
		t.Fatalf("expected run hint, got:\n%s", output)
	}
}

func TestFormatDeployOutput_PartialFailure(t *testing.T) {
	results := []deployResult{
		{AgentName: "a", WorkflowName: strPtr("wf_a"), Success: true},
		{AgentName: "b", WorkflowName: nil, Success: false, Error: "connection refused"},
	}
	output := formatDeployOutput(results)
	if !strings.Contains(output, "1/2") {
		t.Fatalf("expected partial count, got:\n%s", output)
	}
}

func TestFormatDeployOutput_AllFailed(t *testing.T) {
	results := []deployResult{
		{AgentName: "a", WorkflowName: nil, Success: false, Error: "err1"},
	}
	output := formatDeployOutput(results)
	if !strings.Contains(output, "Failed") {
		t.Fatalf("expected failure header, got:\n%s", output)
	}
	if !strings.Contains(output, "agentspan doctor") {
		t.Fatalf("expected doctor hint, got:\n%s", output)
	}
}

func strPtr(s string) *string { return &s }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cli && go test ./cmd/ -run TestFormatDeploy -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement output formatting**

Add to `cli/cmd/deploy.go`:

```go
// formatDeployOutput creates the human-readable deploy result string.
func formatDeployOutput(results []deployResult) string {
	var buf strings.Builder
	succeeded := 0
	for _, r := range results {
		if r.Success {
			succeeded++
		}
	}
	total := len(results)

	if succeeded == total {
		fmt.Fprintf(&buf, "Deployed %d agents:\n", total)
	} else if succeeded > 0 {
		fmt.Fprintf(&buf, "Deployed %d/%d agents:\n", succeeded, total)
	} else {
		fmt.Fprintf(&buf, "Failed to deploy all agents:\n")
	}

	for _, r := range results {
		if r.Success && r.WorkflowName != nil {
			fmt.Fprintf(&buf, "  ✓ %s  →  %s\n", r.AgentName, *r.WorkflowName)
		} else {
			errMsg := r.Error
			if errMsg == "" {
				errMsg = "unknown error"
			}
			fmt.Fprintf(&buf, "  ✗ %s  →  %s\n", r.AgentName, errMsg)
		}
	}

	buf.WriteString("\n")
	if succeeded > 0 {
		buf.WriteString("Run with: agentspan agent run --name <agent> \"your prompt\"\n")
	} else {
		buf.WriteString("Check server status with: agentspan doctor\n")
	}

	return buf.String()
}

// formatDiscoveryTable creates the human-readable discovery confirmation string.
func formatDiscoveryTable(agents []discoveredAgent, pkg string) string {
	var buf strings.Builder
	fmt.Fprintf(&buf, "Discovered %d agents in %s:\n", len(agents), pkg)
	fmt.Fprintf(&buf, "  %-20s %s\n", "Name", "Framework")
	fmt.Fprintf(&buf, "  %-20s %s\n", "────────────────────", "─────────")
	for _, a := range agents {
		fmt.Fprintf(&buf, "  %-20s %s\n", a.Name, a.Framework)
	}
	return buf.String()
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cli && go test ./cmd/ -run TestFormatDeploy -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Implement the Cobra command**

Add to `cli/cmd/deploy.go`:

```go
import (
	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var (
	deployAgents   string
	deployLanguage string
	deployPackage  string
	deployYes      bool
	deployJSON     bool
)

var deployCmd = &cobra.Command{
	Use:   "deploy",
	Short: "Deploy agents from your project to the AgentSpan server",
	Long: `Discover agents in your project code and deploy them to the server.

Automatically detects the project language (Python or TypeScript) and scans
for Agent instances. Use --agents to deploy a subset, --yes to skip confirmation.`,
	RunE: runDeploy,
}

func init() {
	deployCmd.Flags().StringVarP(&deployAgents, "agents", "a", "", "Comma-separated agent names to deploy (default: all)")
	deployCmd.Flags().StringVarP(&deployLanguage, "language", "l", "", "Override language detection (python|typescript)")
	deployCmd.Flags().StringVarP(&deployPackage, "package", "p", "", "Override package/path to scan")
	deployCmd.Flags().BoolVarP(&deployYes, "yes", "y", false, "Skip confirmation prompt")
	deployCmd.Flags().BoolVar(&deployJSON, "json", false, "Output machine-readable JSON")
	rootCmd.AddCommand(deployCmd)
}

func runDeploy(cmd *cobra.Command, args []string) error {
	dir, err := os.Getwd()
	if err != nil {
		return fmt.Errorf("failed to get working directory: %w", err)
	}

	// Step 1: Detect language
	language, err := detectLanguage(dir, deployLanguage)
	if err != nil {
		return err
	}

	// Step 2: Find runtime binary
	var pythonBin string
	if language == "python" {
		pythonBin = findPythonBinary(dir)
		if pythonBin == "" {
			return fmt.Errorf("Python not found. Install Python 3.10+ or use --language typescript")
		}
	} else {
		if _, err := exec.LookPath("npx"); err != nil {
			return fmt.Errorf("npx not found. Install Node.js 18+ or use --language python")
		}
	}

	// Step 3: Infer package
	pkg, err := inferPackage(dir, language, deployPackage)
	if err != nil {
		return err
	}

	// Step 4: Load config and build env
	cfg := getConfig()
	env := buildEnv(cfg)
	ctx := cmd.Context()

	// Step 5: Discover agents
	agents, err := execDiscover(ctx, env, language, pythonBin, pkg)
	if err != nil {
		return fmt.Errorf("agent discovery failed: %w", err)
	}
	if len(agents) == 0 {
		return fmt.Errorf("no agents found in package %q. Define agents as module-level Agent instances", pkg)
	}

	// Step 6: Filter (keep full list for JSON output)
	allDiscovered := agents
	var agentFilter []string
	if deployAgents != "" {
		agentFilter = strings.Split(deployAgents, ",")
	}
	agents, err = filterDiscoveredAgents(agents, agentFilter)
	if err != nil {
		return err
	}

	// Step 7: Confirm
	if !deployYes {
		fmt.Print(formatDiscoveryTable(agents, pkg))
		fmt.Printf("\nDeploy %d agents to %s? [y/N] ", len(agents), cfg.ServerURL)

		var answer string
		fmt.Scanln(&answer)
		if answer != "y" && answer != "Y" {
			return nil
		}
		fmt.Println()
	}

	// Step 8: Deploy
	var agentNames []string
	for _, a := range agents {
		agentNames = append(agentNames, a.Name)
	}
	results, err := execDeploy(ctx, env, language, pythonBin, pkg, agentNames)
	if err != nil {
		return fmt.Errorf("deployment failed: %w", err)
	}

	// Step 9: Output
	succeeded := 0
	for _, r := range results {
		if r.Success {
			succeeded++
		}
	}

	if deployJSON {
		jsonOutput := map[string]interface{}{
			"discovered": allDiscovered, // full list before filtering
			"deployed":   results,
			"summary": map[string]int{
				"total":     len(results),
				"succeeded": succeeded,
				"failed":    len(results) - succeeded,
			},
		}
		printJSON(jsonOutput)
	} else {
		output := formatDeployOutput(results)
		// Colorize
		for _, line := range strings.Split(output, "\n") {
			if strings.HasPrefix(strings.TrimSpace(line), "✓") {
				color.Green("  %s", strings.TrimSpace(line))
			} else if strings.HasPrefix(strings.TrimSpace(line), "✗") {
				color.Red("  %s", strings.TrimSpace(line))
			} else {
				fmt.Println(line)
			}
		}
	}

	// Return error if any failures (Cobra will set exit code 1)
	if succeeded < len(results) {
		return fmt.Errorf("deployment partially failed: %d/%d agents deployed", succeeded, len(results))
	}

	return nil
}

- [ ] **Step 6: Run all tests**

Run: `cd cli && go test ./cmd/ -run "TestDetect|TestInfer|TestFind|TestParse|TestFilter|TestFormat" -v`
Expected: All tests PASS

- [ ] **Step 7: Build and smoke test**

Run: `cd cli && go build -o /tmp/agentspan-test . && /tmp/agentspan-test deploy --help`
Expected: Help text showing all flags

- [ ] **Step 8: Commit**

```bash
git add cli/cmd/deploy.go cli/cmd/deploy_test.go
git commit -m "feat(cli): add agentspan deploy command with discovery, confirmation, and deployment"
```

---

## Chunk 6: Integration Testing

### Task 10: E2E Smoke Test

**Files:**
- Create: `cli/cmd/deploy_integration_test.go`

- [ ] **Step 1: Write integration test with mock subprocess**

```go
// cli/cmd/deploy_integration_test.go
//go:build integration

package cmd

import (
	"os"
	"path/filepath"
	"testing"
)

// TestDeployIntegration_MockSubprocess tests the full flow with a mock Python script.
func TestDeployIntegration_MockSubprocess(t *testing.T) {
	// Create a temporary Python project
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "pyproject.toml"), []byte(`[project]
name = "testapp"
`), 0644)

	// Create a mock Python module that acts as discover/deploy
	mockPkg := filepath.Join(dir, "testapp")
	os.MkdirAll(mockPkg, 0755)
	os.WriteFile(filepath.Join(mockPkg, "__init__.py"), []byte(""), 0644)

	// Test language detection
	lang, err := detectLanguage(dir, "")
	if err != nil {
		t.Fatalf("language detection failed: %v", err)
	}
	if lang != "python" {
		t.Fatalf("expected python, got %s", lang)
	}

	// Test package inference
	pkg, err := inferPackage(dir, "python", "")
	if err != nil {
		t.Fatalf("package inference failed: %v", err)
	}
	if pkg != "testapp" {
		t.Fatalf("expected testapp, got %s", pkg)
	}
}
```

- [ ] **Step 2: Run integration test**

Run: `cd cli && go test ./cmd/ -tags integration -run TestDeployIntegration -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add cli/cmd/deploy_integration_test.go
git commit -m "test(cli): add integration test for deploy command"
```

---

### Task 11: Manual E2E Verification

- [ ] **Step 1: Build the CLI**

Run: `cd cli && go build -o /tmp/agentspan .`

- [ ] **Step 2: Test help output**

Run: `/tmp/agentspan deploy --help`
Expected:
```
Deploy agents from your project to the AgentSpan server
...
Flags:
  -a, --agents string     Comma-separated agent names to deploy (default: all)
      --json               Output machine-readable JSON
  -l, --language string   Override language detection (python|typescript)
  -p, --package string    Override package/path to scan
  -y, --yes               Skip confirmation prompt
```

- [ ] **Step 3: Test error on empty directory**

Run: `cd /tmp && /tmp/agentspan deploy`
Expected: `Error: cannot detect project language. Use --language python|typescript`

- [ ] **Step 4: Test with a Python project**

Create a test project and verify the discovery + deploy flow works end-to-end with a running AgentSpan server.

- [ ] **Step 5: Final commit with any fixes**

```bash
git add -A
git commit -m "fix(cli): post-integration fixes for deploy command"
```

(Skip this commit if no fixes are needed.)
