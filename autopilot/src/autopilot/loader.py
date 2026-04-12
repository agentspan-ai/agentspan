"""Agent loader — reads agent.yaml + workers/*.py and produces an Agent."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

from agentspan.agents import Agent, tool as tool_decorator

from autopilot.registry import get_default_registry


class LoaderError(Exception):
    """Raised when an agent definition cannot be loaded."""


def _import_worker_module(py_path: Path, agent_dir_name: str) -> Any:
    """Import a worker .py file with a unique module name to avoid collisions."""
    tool_name = py_path.stem
    module_name = f"_autopilot_worker_{agent_dir_name}_{tool_name}"

    spec = importlib.util.spec_from_file_location(module_name, py_path)
    if spec is None or spec.loader is None:
        raise LoaderError(f"Cannot import worker file: {py_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _collect_tools_from_module(module: Any) -> List[Any]:
    """Find all @tool-decorated functions in a module."""
    tools = []
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if callable(obj) and hasattr(obj, "_tool_def"):
            tools.append(obj)
    return tools


def _resolve_builtin_tools(tool_refs: List[str]) -> List[Any]:
    """Resolve ``builtin:<integration>`` tool references via the registry."""
    registry = get_default_registry()
    tools: List[Any] = []
    for ref in tool_refs:
        if ref.startswith("builtin:"):
            integration_name = ref[len("builtin:"):]
            integration_tools = registry.get_tools(integration_name)
            if not integration_tools:
                raise LoaderError(
                    f"No tools found for builtin integration: {integration_name!r}"
                )
            tools.extend(integration_tools)
        else:
            raise LoaderError(f"Unknown tool reference format: {ref!r}")
    return tools


def load_agent(agent_dir: Path) -> Agent:
    """Load an agent from a directory containing ``agent.yaml``.

    The directory structure is::

        agent_dir/
            agent.yaml
            workers/
                tool_a.py
                tool_b.py

    Args:
        agent_dir: Path to the agent directory.

    Returns:
        A fully configured :class:`Agent`.

    Raises:
        LoaderError: If the directory or YAML is invalid.
    """
    agent_dir = Path(agent_dir)
    yaml_path = agent_dir / "agent.yaml"

    if not yaml_path.exists():
        raise LoaderError(f"agent.yaml not found in {agent_dir}")

    try:
        with open(yaml_path) as f:
            raw: Dict[str, Any] = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise LoaderError(f"Invalid YAML in {yaml_path}: {exc}") from exc

    # -- Required fields -------------------------------------------------------
    name = raw.get("name")
    if not name:
        raise LoaderError(f"agent.yaml in {agent_dir} is missing required 'name' field")

    model = raw.get("model", "")
    if not model or model.startswith("${"):
        # Default to configured model when empty or a shell variable placeholder
        from autopilot.config import AutopilotConfig
        model = AutopilotConfig.from_env().llm_model
    instructions = raw.get("instructions", "")

    # -- Collect worker tools --------------------------------------------------
    tools: List[Any] = []

    workers_dir = agent_dir / "workers"
    worker_refs = raw.get("tools", [])

    if isinstance(worker_refs, list):
        # Separate builtin refs from file-based worker refs
        builtin_refs = [r for r in worker_refs if isinstance(r, str) and r.startswith("builtin:")]
        file_refs = [r for r in worker_refs if isinstance(r, str) and not r.startswith("builtin:")]

        # Resolve builtin tools
        if builtin_refs:
            tools.extend(_resolve_builtin_tools(builtin_refs))

        # Load file-based workers
        for ref in file_refs:
            worker_file = workers_dir / f"{ref}.py"
            if not worker_file.exists():
                raise LoaderError(
                    f"Worker file not found: {worker_file} "
                    f"(referenced by tool {ref!r} in {yaml_path})"
                )
            module = _import_worker_module(worker_file, agent_dir.name)
            found = _collect_tools_from_module(module)
            if not found:
                raise LoaderError(
                    f"No @tool-decorated functions found in {worker_file}"
                )
            tools.extend(found)

    # -- Credentials -----------------------------------------------------------
    credentials = raw.get("credentials", [])

    # -- Metadata from YAML fields --------------------------------------------
    metadata: Dict[str, Any] = {}

    if "trigger" in raw:
        metadata["trigger"] = raw["trigger"]

    if "error_handling" in raw:
        metadata["error_handling"] = raw["error_handling"]

    if "integrations" in raw:
        metadata["integrations"] = raw["integrations"]

    if "version" in raw:
        metadata["version"] = raw["version"]

    # -- Stateful flag --------------------------------------------------------
    stateful = raw.get("stateful", False)

    return Agent(
        name=name,
        model=model,
        instructions=instructions,
        tools=tools or None,
        credentials=credentials or None,
        metadata=metadata or None,
        stateful=stateful,
    )
