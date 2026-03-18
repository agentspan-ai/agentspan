# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent discovery -- scan Python packages for Agent instances."""

import importlib
import logging
import pkgutil
from typing import List

logger = logging.getLogger("agentspan.agents.runtime.discovery")


def discover_agents(packages: List[str]) -> list:
    """Scan Python packages for module-level Agent instances.

    Imports each package and recursively walks submodules, collecting
    any module-level variable that is an Agent instance.

    Args:
        packages: List of dotted Python package/module names
            (e.g. ``["myapp.agents", "myapp.bots.support"]``).

    Returns:
        List of discovered Agent instances (deduplicated by name).
    """
    from agentspan.agents.agent import Agent

    seen_names: set = set()
    discovered: list = []

    for pkg_name in packages:
        try:
            module = importlib.import_module(pkg_name)
        except ImportError as e:
            logger.warning("Could not import package '%s': %s", pkg_name, e)
            continue

        # Scan this module
        _scan_module(module, Agent, discovered, seen_names)

        # If it's a package, scan submodules recursively
        if hasattr(module, "__path__"):
            for _, submod_name, _ in pkgutil.walk_packages(
                module.__path__, module.__name__ + "."
            ):
                try:
                    submod = importlib.import_module(submod_name)
                    _scan_module(submod, Agent, discovered, seen_names)
                except Exception as e:
                    logger.debug("Could not scan %s: %s", submod_name, e)

    logger.info(
        "Discovered %d agent(s) from packages %s: %s",
        len(discovered),
        packages,
        [a.name for a in discovered],
    )
    return discovered


def _scan_module(module, agent_cls, out, seen):
    """Scan a module's top-level attributes for Agent instances."""
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        obj = getattr(module, attr_name, None)
        if isinstance(obj, agent_cls) and obj.name not in seen:
            out.append(obj)
            seen.add(obj.name)
