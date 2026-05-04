# Agentspan Claw — Foundation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational `autopilot/` module — project scaffolding, agent loader (YAML + Python → Agent object), config management, integration registry, and 3 proof-of-concept integrations (local filesystem, web search, document reader).

**Architecture:** The loader reads `agent.yaml` + dynamically imports Python worker files from `workers/` to construct Agentspan `Agent` objects. An integration registry provides pre-built tools by name. Config management handles `~/.agentspan/autopilot/config.yaml` for server URL, polling intervals, and per-agent state.

**Tech Stack:** Python 3.10+, `uv` for package management, `pyyaml` for YAML parsing, `agentspan` SDK, `markitdown` + `langextract` for document parsing, `httpx` + `trafilatura` for web scraping, Brave Search API for web search.

**Spec:** `docs/design/specs/2026-04-12-agentspan-claw-design.md`

**Related plans:**
- Plan 2: Orchestrator (depends on this plan)
- Plan 3: TUI + Dashboard (depends on this plan)

---

## File Structure

```
autopilot/
├── pyproject.toml                    # uv project, depends on agentspan SDK
├── __init__.py                       # package root
├── loader.py                         # load agent.yaml + workers → Agent object
├── config.py                         # ~/.agentspan/autopilot/config.yaml management
├── registry.py                       # integration registry — lookup pre-built tools by name
├── integrations/
│   ├── __init__.py                   # re-export registry helpers
│   ├── local_fs/
│   │   ├── __init__.py
│   │   └── tools.py                  # read_file, write_file, list_dir, find_files, search_in_files
│   ├── web_search/
│   │   ├── __init__.py
│   │   └── tools.py                  # web_search (Brave API)
│   └── doc_reader/
│       ├── __init__.py
│       └── tools.py                  # read_document (markitdown + langextract fallback)
└── tests/
    ├── __init__.py
    ├── conftest.py                   # shared fixtures (tmp agent dirs, sample YAML)
    ├── test_loader.py                # loader unit tests
    ├── test_config.py                # config management tests
    ├── test_registry.py              # integration registry tests
    └── test_integrations/
        ├── __init__.py
        ├── test_local_fs.py
        ├── test_web_search.py
        └── test_doc_reader.py
```

---

## Chunk 1: Project Scaffolding + Config

### Task 1: Project Setup

**Files:**
- Create: `autopilot/pyproject.toml`
- Create: `autopilot/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "agentspan-autopilot"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "agentspan",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
integrations = [
    "httpx>=0.24",
    "trafilatura>=1.6",
    "markitdown>=0.1",
    "langextract>=0.1",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[tool.setuptools.packages.find]
where = ["."]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `__init__.py`**

```python
"""Agentspan Autopilot — autonomous agent product layer."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Verify project initializes**

Run: `cd autopilot && uv sync --extra dev --extra integrations`
Expected: Dependencies resolve and install successfully.

- [ ] **Step 4: Commit**

```bash
git add autopilot/pyproject.toml autopilot/__init__.py
git commit -m "feat(autopilot): scaffold project with pyproject.toml"
```

---

### Task 2: Config Management

**Files:**
- Create: `autopilot/config.py`
- Create: `autopilot/tests/conftest.py`
- Create: `autopilot/tests/__init__.py`
- Create: `autopilot/tests/test_config.py`

- [ ] **Step 1: Write failing tests for config**

```python
# autopilot/tests/test_config.py
import os
from pathlib import Path

import pytest

from autopilot.config import AutopilotConfig


class TestAutopilotConfig:
    """Test config loading, saving, and defaults."""

    def test_default_config(self):
        """Config has sensible defaults when no file exists."""
        config = AutopilotConfig()
        assert config.server_url == "http://localhost:6767/api"
        assert config.default_model == "openai/gpt-4o"
        assert config.poll_interval_seconds == 30

    def test_config_from_yaml(self, tmp_path):
        """Config loads from a YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "server_url: http://remote:8080/api\n"
            "default_model: anthropic/claude-sonnet-4-20250514\n"
            "poll_interval_seconds: 10\n"
        )
        config = AutopilotConfig.from_file(config_file)
        assert config.server_url == "http://remote:8080/api"
        assert config.default_model == "anthropic/claude-sonnet-4-20250514"
        assert config.poll_interval_seconds == 10

    def test_config_save_and_reload(self, tmp_path):
        """Config round-trips through YAML."""
        config_file = tmp_path / "config.yaml"
        config = AutopilotConfig(server_url="http://example.com/api")
        config.save(config_file)
        reloaded = AutopilotConfig.from_file(config_file)
        assert reloaded.server_url == "http://example.com/api"

    def test_config_env_override(self, monkeypatch):
        """AGENTSPAN_SERVER_URL env var overrides config default."""
        monkeypatch.setenv("AGENTSPAN_SERVER_URL", "http://env-server:9090/api")
        config = AutopilotConfig.from_env()
        assert config.server_url == "http://env-server:9090/api"

    def test_last_seen_tracking(self, tmp_path):
        """Config tracks per-agent last-seen timestamps."""
        config_file = tmp_path / "config.yaml"
        config = AutopilotConfig()
        config.set_last_seen("email-summary", "2026-04-12T08:00:00Z")
        config.save(config_file)
        reloaded = AutopilotConfig.from_file(config_file)
        assert reloaded.get_last_seen("email-summary") == "2026-04-12T08:00:00Z"
        assert reloaded.get_last_seen("nonexistent") is None

    def test_autopilot_dir_default(self):
        """Default autopilot directory is ~/.agentspan/autopilot."""
        config = AutopilotConfig()
        assert config.autopilot_dir == Path.home() / ".agentspan" / "autopilot"

    def test_agents_dir(self):
        """agents_dir is autopilot_dir / agents."""
        config = AutopilotConfig()
        assert config.agents_dir == config.autopilot_dir / "agents"
```

- [ ] **Step 2: Create conftest.py**

```python
# autopilot/tests/conftest.py
```

```python
# autopilot/tests/__init__.py
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd autopilot && uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'autopilot.config'`

- [ ] **Step 4: Implement config module**

```python
# autopilot/config.py
"""Autopilot configuration management.

Manages ~/.agentspan/autopilot/config.yaml — server URL, default model,
polling interval, and per-agent last-seen timestamps for notifications.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


_DEFAULT_SERVER_URL = "http://localhost:6767/api"
_DEFAULT_MODEL = "openai/gpt-4o"
_DEFAULT_POLL_INTERVAL = 30


@dataclass
class AutopilotConfig:
    """Autopilot runtime configuration."""

    server_url: str = _DEFAULT_SERVER_URL
    default_model: str = _DEFAULT_MODEL
    poll_interval_seconds: int = _DEFAULT_POLL_INTERVAL
    autopilot_dir: Path = field(default_factory=lambda: Path.home() / ".agentspan" / "autopilot")
    last_seen: dict[str, str] = field(default_factory=dict)

    @property
    def agents_dir(self) -> Path:
        return self.autopilot_dir / "agents"

    @property
    def orchestrator_dir(self) -> Path:
        return self.autopilot_dir / "orchestrator"

    @classmethod
    def from_file(cls, path: Path) -> AutopilotConfig:
        """Load config from a YAML file."""
        data = yaml.safe_load(path.read_text()) or {}
        return cls(
            server_url=data.get("server_url", _DEFAULT_SERVER_URL),
            default_model=data.get("default_model", _DEFAULT_MODEL),
            poll_interval_seconds=data.get("poll_interval_seconds", _DEFAULT_POLL_INTERVAL),
            autopilot_dir=Path(data.get("autopilot_dir", Path.home() / ".agentspan" / "autopilot")),
            last_seen=data.get("last_seen", {}),
        )

    @classmethod
    def from_env(cls) -> AutopilotConfig:
        """Load config with environment variable overrides."""
        config_path = Path.home() / ".agentspan" / "autopilot" / "config.yaml"
        if config_path.exists():
            config = cls.from_file(config_path)
        else:
            config = cls()
        server_url = os.environ.get("AGENTSPAN_SERVER_URL")
        if server_url:
            config.server_url = server_url
        model = os.environ.get("AGENTSPAN_LLM_MODEL")
        if model:
            config.default_model = model
        return config

    def save(self, path: Path) -> None:
        """Save config to a YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "server_url": self.server_url,
            "default_model": self.default_model,
            "poll_interval_seconds": self.poll_interval_seconds,
        }
        if str(self.autopilot_dir) != str(Path.home() / ".agentspan" / "autopilot"):
            data["autopilot_dir"] = str(self.autopilot_dir)
        if self.last_seen:
            data["last_seen"] = self.last_seen
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    def set_last_seen(self, agent_name: str, timestamp: str) -> None:
        """Track the last-seen timestamp for an agent's notifications."""
        self.last_seen[agent_name] = timestamp

    def get_last_seen(self, agent_name: str) -> Optional[str]:
        """Get the last-seen timestamp for an agent, or None."""
        return self.last_seen.get(agent_name)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd autopilot && uv run pytest tests/test_config.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add autopilot/config.py autopilot/tests/
git commit -m "feat(autopilot): add config management with YAML persistence"
```

---

## Chunk 2: Agent Loader

### Task 3: Agent Loader — YAML + Python Workers → Agent Object

**Files:**
- Create: `autopilot/loader.py`
- Create: `autopilot/tests/test_loader.py`

- [ ] **Step 1: Write failing tests for the loader**

```python
# autopilot/tests/test_loader.py
"""Tests for loading agent definitions from disk."""

from pathlib import Path
from textwrap import dedent

import pytest

from autopilot.loader import load_agent, LoaderError


@pytest.fixture
def agent_dir(tmp_path):
    """Create a minimal agent directory with YAML and one worker."""
    d = tmp_path / "test-agent"
    d.mkdir()
    (d / "agent.yaml").write_text(dedent("""\
        name: test-agent
        version: 1
        model: openai/gpt-4o
        instructions: You are a test agent.
        tools:
          - greet
        max_turns: 10
    """))
    workers = d / "workers"
    workers.mkdir()
    (workers / "greet.py").write_text(dedent("""\
        from agentspan.agents import tool

        @tool
        def greet(name: str) -> str:
            \"\"\"Greet someone by name.\"\"\"
            return f"Hello, {name}!"
    """))
    return d


@pytest.fixture
def agent_dir_no_tools(tmp_path):
    """Agent directory with no tools declared."""
    d = tmp_path / "simple-agent"
    d.mkdir()
    (d / "agent.yaml").write_text(dedent("""\
        name: simple-agent
        version: 1
        model: openai/gpt-4o
        instructions: You are simple.
    """))
    return d


@pytest.fixture
def agent_dir_with_credentials(tmp_path):
    """Agent directory with credentials declared."""
    d = tmp_path / "cred-agent"
    d.mkdir()
    (d / "agent.yaml").write_text(dedent("""\
        name: cred-agent
        version: 1
        model: openai/gpt-4o
        instructions: You need creds.
        tools:
          - api_caller
        credentials:
          - MY_API_KEY
    """))
    workers = d / "workers"
    workers.mkdir()
    (workers / "api_caller.py").write_text(dedent("""\
        from agentspan.agents import tool

        @tool(credentials=["MY_API_KEY"])
        def api_caller(query: str) -> str:
            \"\"\"Call an API.\"\"\"
            return f"result for {query}"
    """))
    return d


class TestLoadAgent:
    """Test loading agents from disk."""

    def test_load_basic_agent(self, agent_dir):
        """Load an agent with one tool from YAML + worker file."""
        agent = load_agent(agent_dir)
        assert agent.name == "test-agent"
        assert agent.model == "openai/gpt-4o"
        assert "You are a test agent." in agent.instructions
        assert agent.max_turns == 10
        assert len(agent.tools) == 1
        assert agent.tools[0]._tool_def.name == "greet"

    def test_load_agent_no_tools(self, agent_dir_no_tools):
        """Load an agent with no tools."""
        agent = load_agent(agent_dir_no_tools)
        assert agent.name == "simple-agent"
        assert agent.tools is None or len(agent.tools) == 0

    def test_load_agent_with_credentials(self, agent_dir_with_credentials):
        """Load an agent that declares credentials."""
        agent = load_agent(agent_dir_with_credentials)
        assert agent.name == "cred-agent"
        assert agent.credentials == ["MY_API_KEY"]

    def test_load_agent_missing_yaml(self, tmp_path):
        """Raise LoaderError if agent.yaml is missing."""
        d = tmp_path / "no-yaml"
        d.mkdir()
        with pytest.raises(LoaderError, match="agent.yaml not found"):
            load_agent(d)

    def test_load_agent_missing_worker(self, tmp_path):
        """Raise LoaderError if a declared tool has no worker file."""
        d = tmp_path / "missing-worker"
        d.mkdir()
        (d / "agent.yaml").write_text(dedent("""\
            name: bad-agent
            version: 1
            model: openai/gpt-4o
            instructions: missing worker
            tools:
              - nonexistent
        """))
        with pytest.raises(LoaderError, match="nonexistent"):
            load_agent(d)

    def test_load_agent_invalid_yaml(self, tmp_path):
        """Raise LoaderError if agent.yaml is malformed."""
        d = tmp_path / "bad-yaml"
        d.mkdir()
        (d / "agent.yaml").write_text("name: [invalid yaml {{{")
        with pytest.raises(LoaderError):
            load_agent(d)

    def test_load_agent_missing_name(self, tmp_path):
        """Raise LoaderError if name field is missing."""
        d = tmp_path / "no-name"
        d.mkdir()
        (d / "agent.yaml").write_text(dedent("""\
            version: 1
            model: openai/gpt-4o
            instructions: no name field
        """))
        with pytest.raises(LoaderError, match="name"):
            load_agent(d)

    def test_load_agent_with_trigger(self, tmp_path):
        """Trigger config is preserved in agent metadata."""
        d = tmp_path / "cron-agent"
        d.mkdir()
        (d / "agent.yaml").write_text(dedent("""\
            name: cron-agent
            version: 1
            model: openai/gpt-4o
            instructions: I run on a schedule.
            trigger:
              type: cron
              schedule: "0 8 * * *"
        """))
        agent = load_agent(d)
        assert agent.metadata["trigger"]["type"] == "cron"
        assert agent.metadata["trigger"]["schedule"] == "0 8 * * *"

    def test_load_agent_with_stateful(self, tmp_path):
        """Stateful flag is passed through."""
        d = tmp_path / "stateful-agent"
        d.mkdir()
        (d / "agent.yaml").write_text(dedent("""\
            name: stateful-agent
            version: 1
            model: openai/gpt-4o
            instructions: I am stateful.
            stateful: true
        """))
        agent = load_agent(d)
        assert agent.stateful is True

    def test_load_agent_with_integration_tools(self, tmp_path):
        """Tools prefixed with 'builtin:' are resolved from the integration registry."""
        d = tmp_path / "integrated-agent"
        d.mkdir()
        (d / "agent.yaml").write_text(dedent("""\
            name: integrated-agent
            version: 1
            model: openai/gpt-4o
            instructions: I use integrations.
            tools:
              - builtin:local_fs
        """))
        agent = load_agent(d)
        # local_fs integration provides multiple tools
        assert len(agent.tools) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autopilot && uv run pytest tests/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'autopilot.loader'`

- [ ] **Step 3: Implement the loader**

```python
# autopilot/loader.py
"""Agent loader — reads agent.yaml + worker Python files from disk and constructs Agent objects."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

from agentspan.agents import Agent


class LoaderError(Exception):
    """Raised when an agent cannot be loaded from disk."""


def load_agent(agent_dir: Path, registry: Any = None) -> Agent:
    """Load an Agent from a directory containing agent.yaml and optional workers/.

    Args:
        agent_dir: Path to the agent directory.
        registry: Optional integration registry for resolving builtin: tool references.
                  If None, uses the default registry.

    Returns:
        A fully constructed Agent object ready for runtime.start().

    Raises:
        LoaderError: If the directory is invalid, YAML is malformed, or workers are missing.
    """
    agent_dir = Path(agent_dir)
    yaml_path = agent_dir / "agent.yaml"

    if not yaml_path.exists():
        raise LoaderError(f"agent.yaml not found in {agent_dir}")

    try:
        config = yaml.safe_load(yaml_path.read_text())
    except yaml.YAMLError as e:
        raise LoaderError(f"Invalid YAML in {yaml_path}: {e}") from e

    if not isinstance(config, dict):
        raise LoaderError(f"agent.yaml must be a YAML mapping, got {type(config).__name__}")

    if "name" not in config:
        raise LoaderError(f"agent.yaml in {agent_dir} is missing required field 'name'")

    # Load tools
    tools = _load_tools(agent_dir, config.get("tools", []), registry)

    # Build metadata with trigger and version info
    metadata = config.get("metadata", {})
    if "trigger" in config:
        metadata["trigger"] = config["trigger"]
    if "version" in config:
        metadata["version"] = config["version"]

    # Build agent kwargs from YAML fields
    kwargs: dict[str, Any] = {
        "name": config["name"],
        "model": config.get("model", ""),
        "instructions": config.get("instructions", ""),
        "max_turns": config.get("max_turns", 25),
        "metadata": metadata,
    }

    if tools:
        kwargs["tools"] = tools

    if "credentials" in config:
        kwargs["credentials"] = config["credentials"]

    if config.get("stateful"):
        kwargs["stateful"] = True

    if "max_tokens" in config:
        kwargs["max_tokens"] = config["max_tokens"]

    if "temperature" in config:
        kwargs["temperature"] = config["temperature"]

    return Agent(**kwargs)


def _load_tools(agent_dir: Path, tool_names: list[str], registry: Any) -> list:
    """Load tools by name — either from workers/ directory or integration registry."""
    if not tool_names:
        return []

    if registry is None:
        from autopilot.registry import get_default_registry

        registry = get_default_registry()

    tools = []
    workers_dir = agent_dir / "workers"

    for tool_name in tool_names:
        if tool_name.startswith("builtin:"):
            # Resolve from integration registry
            integration_name = tool_name[len("builtin:"):]
            integration_tools = registry.get_tools(integration_name)
            if not integration_tools:
                raise LoaderError(
                    f"Unknown builtin integration '{integration_name}'. "
                    f"Available: {', '.join(registry.list_integrations())}"
                )
            tools.extend(integration_tools)
        else:
            # Load from workers/ directory
            tool_func = _load_worker_tool(workers_dir, tool_name)
            tools.append(tool_func)

    return tools


def _load_worker_tool(workers_dir: Path, tool_name: str):
    """Dynamically import a @tool-decorated function from workers/{tool_name}.py."""
    worker_file = workers_dir / f"{tool_name}.py"
    if not worker_file.exists():
        raise LoaderError(
            f"Worker file not found: {worker_file}. "
            f"Declare tool '{tool_name}' or create {worker_file}"
        )

    module_name = f"_autopilot_worker_{tool_name}"
    spec = importlib.util.spec_from_file_location(module_name, worker_file)
    if spec is None or spec.loader is None:
        raise LoaderError(f"Cannot load Python module from {worker_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise LoaderError(f"Error loading worker {worker_file}: {e}") from e

    # Find the @tool-decorated function matching the tool_name
    tool_func = _find_tool_in_module(module, tool_name)
    if tool_func is None:
        raise LoaderError(
            f"No @tool-decorated function named '{tool_name}' found in {worker_file}. "
            f"The function must be decorated with @tool and named '{tool_name}'."
        )

    return tool_func


def _find_tool_in_module(module, tool_name: str):
    """Find a @tool-decorated function in a module, matching by tool name."""
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if callable(obj) and hasattr(obj, "_tool_def"):
            if obj._tool_def.name == tool_name:
                return obj
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd autopilot && uv run pytest tests/test_loader.py -v`
Expected: Most tests pass. The `test_load_agent_with_integration_tools` test may fail until the registry is implemented (Task 4).

- [ ] **Step 5: Commit**

```bash
git add autopilot/loader.py autopilot/tests/test_loader.py
git commit -m "feat(autopilot): add agent loader — YAML + Python workers to Agent object"
```

---

## Chunk 3: Integration Registry + First Integrations

### Task 4: Integration Registry

**Files:**
- Create: `autopilot/registry.py`
- Create: `autopilot/integrations/__init__.py`
- Create: `autopilot/tests/test_registry.py`

- [ ] **Step 1: Write failing tests for registry**

```python
# autopilot/tests/test_registry.py
"""Tests for the integration registry."""

import pytest

from autopilot.registry import IntegrationRegistry, get_default_registry


class TestIntegrationRegistry:
    """Test integration registration and lookup."""

    def test_register_and_get(self):
        """Register an integration and retrieve its tools."""
        registry = IntegrationRegistry()

        def fake_tool():
            pass
        fake_tool._tool_def = type("ToolDef", (), {"name": "fake"})()

        registry.register("test_integration", [fake_tool])
        tools = registry.get_tools("test_integration")
        assert len(tools) == 1

    def test_get_unknown_returns_empty(self):
        """Unknown integration returns empty list."""
        registry = IntegrationRegistry()
        assert registry.get_tools("nonexistent") == []

    def test_list_integrations(self):
        """List all registered integration names."""
        registry = IntegrationRegistry()

        def fake_tool():
            pass
        fake_tool._tool_def = type("ToolDef", (), {"name": "fake"})()

        registry.register("alpha", [fake_tool])
        registry.register("beta", [fake_tool])
        names = registry.list_integrations()
        assert "alpha" in names
        assert "beta" in names

    def test_default_registry_has_local_fs(self):
        """Default registry includes the local_fs integration."""
        registry = get_default_registry()
        assert "local_fs" in registry.list_integrations()
        tools = registry.get_tools("local_fs")
        assert len(tools) >= 1

    def test_default_registry_has_web_search(self):
        """Default registry includes the web_search integration."""
        registry = get_default_registry()
        assert "web_search" in registry.list_integrations()

    def test_default_registry_has_doc_reader(self):
        """Default registry includes the doc_reader integration."""
        registry = get_default_registry()
        assert "doc_reader" in registry.list_integrations()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autopilot && uv run pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'autopilot.registry'`

- [ ] **Step 3: Implement registry**

```python
# autopilot/registry.py
"""Integration registry — lookup pre-built tools by integration name."""

from __future__ import annotations

from typing import Any


class IntegrationRegistry:
    """Registry of pre-built integration tool sets."""

    def __init__(self) -> None:
        self._integrations: dict[str, list[Any]] = {}

    def register(self, name: str, tools: list[Any]) -> None:
        """Register an integration's tools under a name."""
        self._integrations[name] = tools

    def get_tools(self, name: str) -> list[Any]:
        """Get all tools for an integration, or empty list if unknown."""
        return self._integrations.get(name, [])

    def list_integrations(self) -> list[str]:
        """List all registered integration names."""
        return sorted(self._integrations.keys())


_default_registry: IntegrationRegistry | None = None


def get_default_registry() -> IntegrationRegistry:
    """Get the singleton default registry with all built-in integrations loaded."""
    global _default_registry
    if _default_registry is None:
        _default_registry = IntegrationRegistry()
        _register_builtins(_default_registry)
    return _default_registry


def _register_builtins(registry: IntegrationRegistry) -> None:
    """Register all built-in integrations."""
    from autopilot.integrations.local_fs.tools import get_tools as local_fs_tools
    from autopilot.integrations.web_search.tools import get_tools as web_search_tools
    from autopilot.integrations.doc_reader.tools import get_tools as doc_reader_tools

    registry.register("local_fs", local_fs_tools())
    registry.register("web_search", web_search_tools())
    registry.register("doc_reader", doc_reader_tools())
```

```python
# autopilot/integrations/__init__.py
"""Built-in integrations for Agentspan Autopilot."""
```

- [ ] **Step 4: Run registry tests (will fail — integrations not yet implemented)**

Run: `cd autopilot && uv run pytest tests/test_registry.py::TestIntegrationRegistry::test_register_and_get tests/test_registry.py::TestIntegrationRegistry::test_get_unknown_returns_empty tests/test_registry.py::TestIntegrationRegistry::test_list_integrations -v`
Expected: First 3 tests PASS (core registry logic). Last 3 will fail until integrations exist.

- [ ] **Step 5: Commit**

```bash
git add autopilot/registry.py autopilot/integrations/__init__.py autopilot/tests/test_registry.py
git commit -m "feat(autopilot): add integration registry with registration and lookup"
```

---

### Task 5: Local Filesystem Integration

**Files:**
- Create: `autopilot/integrations/local_fs/__init__.py`
- Create: `autopilot/integrations/local_fs/tools.py`
- Create: `autopilot/tests/test_integrations/__init__.py`
- Create: `autopilot/tests/test_integrations/test_local_fs.py`

- [ ] **Step 1: Write failing tests**

```python
# autopilot/tests/test_integrations/test_local_fs.py
"""Tests for local filesystem integration tools."""

from pathlib import Path

import pytest

from autopilot.integrations.local_fs.tools import get_tools


@pytest.fixture
def fs_tools():
    """Get all local_fs tools as a dict keyed by tool name."""
    tools = get_tools()
    return {t._tool_def.name: t for t in tools}


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace with test files."""
    (tmp_path / "hello.txt").write_text("Hello, world!")
    (tmp_path / "data.csv").write_text("a,b,c\n1,2,3\n")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.py").write_text("print('nested')")
    return tmp_path


class TestLocalFsTools:
    """Test local filesystem tools."""

    def test_get_tools_returns_list(self):
        """get_tools returns a non-empty list of @tool-decorated functions."""
        tools = get_tools()
        assert len(tools) >= 3
        for t in tools:
            assert hasattr(t, "_tool_def")

    def test_read_file(self, fs_tools, workspace):
        """read_file returns file contents."""
        result = fs_tools["read_file"](path=str(workspace / "hello.txt"))
        assert "Hello, world!" in result

    def test_read_file_not_found(self, fs_tools, workspace):
        """read_file returns error for missing file."""
        result = fs_tools["read_file"](path=str(workspace / "nope.txt"))
        assert "Error" in result or "not found" in result.lower()

    def test_write_file(self, fs_tools, workspace):
        """write_file creates a new file."""
        target = str(workspace / "new.txt")
        result = fs_tools["write_file"](path=target, content="new content")
        assert Path(target).read_text() == "new content"

    def test_list_dir(self, fs_tools, workspace):
        """list_dir shows directory contents."""
        result = fs_tools["list_dir"](path=str(workspace))
        assert "hello.txt" in result
        assert "subdir" in result

    def test_find_files(self, fs_tools, workspace):
        """find_files matches glob patterns."""
        result = fs_tools["find_files"](pattern="**/*.py", path=str(workspace))
        assert "nested.py" in result

    def test_search_in_files(self, fs_tools, workspace):
        """search_in_files finds regex matches."""
        result = fs_tools["search_in_files"](regex="Hello", path=str(workspace))
        assert "hello.txt" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autopilot && uv run pytest tests/test_integrations/test_local_fs.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement local_fs tools**

```python
# autopilot/integrations/local_fs/__init__.py
"""Local filesystem integration."""
```

```python
# autopilot/integrations/local_fs/tools.py
"""Local filesystem tools — read, write, list, find, search files."""

from __future__ import annotations

import re
from pathlib import Path

from agentspan.agents import tool

_MAX_FILE_BYTES = 200_000
_MAX_SEARCH_RESULTS = 100


@tool
def read_file(path: str) -> str:
    """Read a file and return its text contents."""
    target = Path(path)
    if not target.exists():
        return f"Error: '{path}' not found."
    if target.is_dir():
        return f"Error: '{path}' is a directory. Use list_dir."
    size = target.stat().st_size
    if size > _MAX_FILE_BYTES:
        return f"Error: '{path}' is {size:,} bytes (limit {_MAX_FILE_BYTES:,})."
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading '{path}': {e}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content):,} bytes to '{path}'."
    except Exception as e:
        return f"Error writing '{path}': {e}"


@tool
def list_dir(path: str = ".") -> str:
    """List directory contents with file sizes."""
    target = Path(path)
    if not target.exists():
        return f"Error: '{path}' not found."
    if not target.is_dir():
        return f"Error: '{path}' is not a directory."
    try:
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries:
            if entry.is_dir():
                lines.append(f"  {entry.name}/")
            else:
                lines.append(f"  {entry.name}  ({entry.stat().st_size:,} bytes)")
        header = str(target) + "/"
        return header + "\n" + "\n".join(lines) if lines else header + " (empty)"
    except Exception as e:
        return f"Error listing '{path}': {e}"


@tool
def find_files(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern (e.g. '**/*.py')."""
    base = Path(path)
    if not base.exists():
        return f"Error: '{path}' not found."
    try:
        matches = sorted(m for m in base.glob(pattern) if m.is_file())
        if not matches:
            return f"No files matching '{pattern}' under '{path}'."
        lines = [str(m) for m in matches[:200]]
        suffix = f"\n... ({len(matches) - 200} more)" if len(matches) > 200 else ""
        return "\n".join(lines) + suffix
    except Exception as e:
        return f"Error finding files: {e}"


@tool
def search_in_files(regex: str, path: str = ".", file_glob: str = "**/*") -> str:
    """Search for a regex pattern in file contents. Returns file:line: match entries."""
    base = Path(path)
    try:
        compiled = re.compile(regex)
    except re.error as e:
        return f"Invalid regex '{regex}': {e}"
    results = []
    for filepath in sorted(base.glob(file_glob)):
        if not filepath.is_file() or filepath.stat().st_size > _MAX_FILE_BYTES:
            continue
        try:
            for lineno, line in enumerate(
                filepath.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if compiled.search(line):
                    results.append(f"{filepath}:{lineno}: {line.rstrip()}")
                    if len(results) >= _MAX_SEARCH_RESULTS:
                        break
        except Exception:
            continue
        if len(results) >= _MAX_SEARCH_RESULTS:
            break
    if not results:
        return f"No matches for '{regex}' in '{path}'."
    suffix = "\n... (truncated)" if len(results) >= _MAX_SEARCH_RESULTS else ""
    return "\n".join(results) + suffix


def get_tools() -> list:
    """Return all local_fs tools."""
    return [read_file, write_file, list_dir, find_files, search_in_files]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd autopilot && uv run pytest tests/test_integrations/test_local_fs.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add autopilot/integrations/local_fs/ autopilot/tests/test_integrations/
git commit -m "feat(autopilot): add local filesystem integration tools"
```

---

### Task 6: Web Search Integration

**Files:**
- Create: `autopilot/integrations/web_search/__init__.py`
- Create: `autopilot/integrations/web_search/tools.py`
- Create: `autopilot/tests/test_integrations/test_web_search.py`

- [ ] **Step 1: Write failing tests**

```python
# autopilot/tests/test_integrations/test_web_search.py
"""Tests for web search integration tools."""

from unittest.mock import patch, MagicMock

import pytest

from autopilot.integrations.web_search.tools import get_tools, web_search


class TestWebSearchTools:
    """Test web search tools."""

    def test_get_tools_returns_list(self):
        """get_tools returns tool list."""
        tools = get_tools()
        assert len(tools) >= 1
        assert all(hasattr(t, "_tool_def") for t in tools)

    def test_web_search_tool_name(self):
        """web_search tool has correct name."""
        assert web_search._tool_def.name == "web_search"

    @patch("autopilot.integrations.web_search.tools.httpx")
    def test_web_search_success(self, mock_httpx):
        """web_search returns formatted results on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://example.com",
                        "description": "A test result description.",
                    }
                ]
            }
        }
        mock_httpx.get.return_value = mock_response

        result = web_search(query="test query")
        assert "Test Result" in result
        assert "https://example.com" in result

    @patch("autopilot.integrations.web_search.tools.httpx")
    def test_web_search_no_results(self, mock_httpx):
        """web_search handles no results gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"web": {"results": []}}
        mock_httpx.get.return_value = mock_response

        result = web_search(query="obscure query")
        assert "no results" in result.lower() or result == ""

    def test_web_search_missing_api_key(self):
        """web_search returns error when API key is not set."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove any existing key
            import os
            os.environ.pop("BRAVE_API_KEY", None)
            result = web_search(query="test")
            assert "error" in result.lower() or "api key" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autopilot && uv run pytest tests/test_integrations/test_web_search.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement web search tool**

```python
# autopilot/integrations/web_search/__init__.py
"""Web search integration."""
```

```python
# autopilot/integrations/web_search/tools.py
"""Web search tool using Brave Search API."""

from __future__ import annotations

import os

import httpx

from agentspan.agents import tool

_MAX_RESULTS = 10


@tool(credentials=["BRAVE_API_KEY"])
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web and return results with titles, URLs, and descriptions."""
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        return "Error: BRAVE_API_KEY not set. Set it with: agentspan credentials set BRAVE_API_KEY"

    num_results = min(num_results, _MAX_RESULTS)
    try:
        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": num_results},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
    except Exception as e:
        return f"Error searching: {e}"

    data = response.json()
    results = data.get("web", {}).get("results", [])
    if not results:
        return f"No results found for '{query}'."

    lines = []
    for r in results[:num_results]:
        title = r.get("title", "")
        url = r.get("url", "")
        desc = r.get("description", "")
        lines.append(f"**{title}**\n{url}\n{desc}\n")

    return "\n".join(lines)


def get_tools() -> list:
    """Return all web search tools."""
    return [web_search]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd autopilot && uv run pytest tests/test_integrations/test_web_search.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add autopilot/integrations/web_search/ autopilot/tests/test_integrations/test_web_search.py
git commit -m "feat(autopilot): add web search integration (Brave API)"
```

---

### Task 7: Document Reader Integration

**Files:**
- Create: `autopilot/integrations/doc_reader/__init__.py`
- Create: `autopilot/integrations/doc_reader/tools.py`
- Create: `autopilot/tests/test_integrations/test_doc_reader.py`

- [ ] **Step 1: Write failing tests**

```python
# autopilot/tests/test_integrations/test_doc_reader.py
"""Tests for document reader integration tools."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from autopilot.integrations.doc_reader.tools import get_tools, read_document


@pytest.fixture
def txt_file(tmp_path):
    """Create a plain text file."""
    f = tmp_path / "test.txt"
    f.write_text("This is a plain text document.")
    return f


@pytest.fixture
def html_file(tmp_path):
    """Create an HTML file."""
    f = tmp_path / "test.html"
    f.write_text("<html><body><h1>Title</h1><p>Content here.</p></body></html>")
    return f


class TestDocReaderTools:
    """Test document reader tools."""

    def test_get_tools_returns_list(self):
        """get_tools returns a non-empty list."""
        tools = get_tools()
        assert len(tools) >= 1
        assert all(hasattr(t, "_tool_def") for t in tools)

    def test_read_document_tool_name(self):
        """read_document tool has correct name."""
        assert read_document._tool_def.name == "read_document"

    def test_read_plain_text(self, txt_file):
        """read_document handles plain text files directly."""
        result = read_document(path=str(txt_file))
        assert "plain text document" in result

    def test_read_file_not_found(self):
        """read_document returns error for missing file."""
        result = read_document(path="/nonexistent/file.pdf")
        assert "error" in result.lower() or "not found" in result.lower()

    def test_read_document_uses_markitdown(self, tmp_path):
        """read_document attempts markitdown for supported formats."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake pdf content")

        with patch("autopilot.integrations.doc_reader.tools._try_markitdown") as mock_md:
            mock_md.return_value = "# Converted Content\nFrom markitdown."
            result = read_document(path=str(pdf_file))
            mock_md.assert_called_once()
            assert "Converted Content" in result

    def test_read_document_fallback_to_langextract(self, tmp_path):
        """read_document falls back to langextract when markitdown fails."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake pdf content")

        with patch("autopilot.integrations.doc_reader.tools._try_markitdown") as mock_md, \
             patch("autopilot.integrations.doc_reader.tools._try_langextract") as mock_le:
            mock_md.return_value = None  # markitdown fails
            mock_le.return_value = "Extracted via langextract."
            result = read_document(path=str(pdf_file))
            mock_le.assert_called_once()
            assert "langextract" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autopilot && uv run pytest tests/test_integrations/test_doc_reader.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement document reader tool**

```python
# autopilot/integrations/doc_reader/__init__.py
"""Document reader integration."""
```

```python
# autopilot/integrations/doc_reader/tools.py
"""Document reader tool — converts PDF, DOCX, XLSX, etc. to text using markitdown + langextract."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agentspan.agents import tool

_PLAIN_TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".tsv", ".log", ".json", ".xml", ".yaml", ".yml"}
_MAX_FILE_BYTES = 50_000_000  # 50MB


@tool
def read_document(path: str) -> str:
    """Read a document (PDF, DOCX, XLSX, PPTX, HTML, images, or text) and return its content as text.

    Uses markitdown for broad format support, with langextract as fallback for complex PDFs.
    """
    target = Path(path)
    if not target.exists():
        return f"Error: '{path}' not found."
    if target.is_dir():
        return f"Error: '{path}' is a directory."
    if target.stat().st_size > _MAX_FILE_BYTES:
        return f"Error: '{path}' is too large ({target.stat().st_size:,} bytes, limit {_MAX_FILE_BYTES:,})."

    # Plain text files — read directly
    if target.suffix.lower() in _PLAIN_TEXT_EXTENSIONS:
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading '{path}': {e}"

    # Try markitdown first (broader format support, faster)
    result = _try_markitdown(target)
    if result:
        return result

    # Fallback to langextract for PDFs with complex layouts
    if target.suffix.lower() == ".pdf":
        result = _try_langextract(target)
        if result:
            return result

    return f"Error: could not extract text from '{path}'. Unsupported format or extraction failed."


def _try_markitdown(path: Path) -> Optional[str]:
    """Attempt to convert a document using markitdown."""
    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(str(path))
        text = result.text_content if hasattr(result, "text_content") else str(result)
        return text if text and text.strip() else None
    except ImportError:
        return None
    except Exception:
        return None


def _try_langextract(path: Path) -> Optional[str]:
    """Attempt to extract text from a PDF using langextract."""
    try:
        from langextract import extract

        result = extract(str(path))
        text = result if isinstance(result, str) else str(result)
        return text if text and text.strip() else None
    except ImportError:
        return None
    except Exception:
        return None


def get_tools() -> list:
    """Return all document reader tools."""
    return [read_document]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd autopilot && uv run pytest tests/test_integrations/test_doc_reader.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add autopilot/integrations/doc_reader/ autopilot/tests/test_integrations/test_doc_reader.py
git commit -m "feat(autopilot): add document reader integration (markitdown + langextract)"
```

---

### Task 8: Wire Everything Together + Full Test Pass

**Files:**
- Modify: `autopilot/tests/test_registry.py` (already written)
- Modify: `autopilot/tests/test_loader.py` (already written)

- [ ] **Step 1: Run the full registry tests now that integrations exist**

Run: `cd autopilot && uv run pytest tests/test_registry.py -v`
Expected: All 6 tests PASS (including default registry tests).

- [ ] **Step 2: Run the full loader tests now that registry exists**

Run: `cd autopilot && uv run pytest tests/test_loader.py -v`
Expected: All 10 tests PASS (including `test_load_agent_with_integration_tools`).

- [ ] **Step 3: Run the entire test suite**

Run: `cd autopilot && uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 4: Lint**

Run: `cd autopilot && uv run ruff check . && uv run ruff format --check .`
Expected: No lint or formatting errors.

- [ ] **Step 5: Fix any lint issues**

Run: `cd autopilot && uv run ruff format . && uv run ruff check --fix .`

- [ ] **Step 6: Final commit**

```bash
git add -A autopilot/
git commit -m "feat(autopilot): complete foundation — loader, config, registry, 3 integrations"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Project scaffolding (pyproject.toml) | uv sync |
| 2 | Config management (YAML, env vars, last-seen tracking) | 7 tests |
| 3 | Agent loader (YAML + Python workers → Agent) | 10 tests |
| 4 | Integration registry (register, lookup, list) | 6 tests |
| 5 | Local filesystem integration (read, write, list, find, search) | 7 tests |
| 6 | Web search integration (Brave API) | 5 tests |
| 7 | Document reader integration (markitdown + langextract) | 5 tests |
| 8 | Integration test — full pass | All above |

**Total: ~40 tests, 8 tasks, ~12 files.**

After this plan, the foundation is in place for Plan 2 (Orchestrator) and Plan 3 (TUI).
