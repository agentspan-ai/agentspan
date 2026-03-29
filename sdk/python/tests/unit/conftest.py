# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit-test fixtures — clears global dispatch state between tests."""

import pytest


@pytest.fixture(autouse=True)
def _clear_tool_def_registry():
    """Clear the module-level _tool_def_registry before each test.

    ``make_tool_worker()`` stores tool definitions in a global dict keyed by
    tool name so they survive spawn-mode multiprocessing.  Without cleanup,
    a tool named ``my_tool`` registered with ``credentials=["X"]`` in one test
    poisons every subsequent test that reuses the same name.
    """
    from agentspan.agents.runtime._dispatch import _tool_def_registry

    _tool_def_registry.clear()
