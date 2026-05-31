# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for LangGraph/LangChain framework auto-detection in serializer.py."""
import pytest
from unittest.mock import MagicMock


def _make_obj_with_class_name(class_name: str):
    """Create a mock object whose type(obj).__name__ is class_name."""
    obj = MagicMock()
    type(obj).__name__ = class_name
    return obj


def test_detect_compiled_state_graph():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("CompiledStateGraph")
    assert detect_framework(obj) == "langgraph"


def test_detect_pregel():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("Pregel")
    assert detect_framework(obj) == "langgraph"


def test_detect_agent_executor():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("AgentExecutor")
    assert detect_framework(obj) == "langchain"


def test_openai_agent_still_detected():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = MagicMock()
    type(obj).__name__ = "Agent"
    type(obj).__module__ = "agents.core"
    assert detect_framework(obj) == "openai"


def test_native_agent_returns_none():
    from agentspan.agents.frameworks.serializer import detect_framework
    # A plain MagicMock with agentspan module but not an isinstance(obj, Agent)
    # The module prefix "agentspan.agents.agent" doesn't match any _FRAMEWORK_DETECTION prefix
    obj = MagicMock()
    type(obj).__name__ = "Agent"
    type(obj).__module__ = "agentspan.agents.agent"
    result = detect_framework(obj)
    assert result is None


def test_unknown_object_returns_none():
    from agentspan.agents.frameworks.serializer import detect_framework
    obj = _make_obj_with_class_name("SomeRandomClass")
    type(obj).__module__ = "some.unknown.module"
    assert detect_framework(obj) is None
