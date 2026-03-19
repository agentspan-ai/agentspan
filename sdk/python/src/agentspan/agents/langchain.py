# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""User-facing create_agent wrapper for LangChain/LangGraph agents.

Import from here instead of langchain.agents so that Agentspan can
extract the LLM model, tools, and instructions for proper server-side
orchestration (AI_MODEL + SIMPLE tasks — same as OpenAI/ADK).

Usage::

    from agentspan.agents.langchain import create_agent
    from langchain_openai import ChatOpenAI
    from langchain_core.tools import tool

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    @tool
    def my_tool(x: str) -> str:
        \"\"\"Does something.\"\"\"
        return x

    graph = create_agent(llm, tools=[my_tool], name="my_agent")

    with AgentRuntime() as runtime:
        result = runtime.run(graph, "prompt")
"""

from __future__ import annotations

from typing import Any, List, Optional, Union


def create_agent(
    model: Any,
    *,
    tools: Optional[List[Any]] = None,
    name: Optional[str] = None,
    system_prompt: Optional[Union[str, Any]] = None,
    **kwargs: Any,
) -> Any:
    """Agentspan wrapper around ``langchain.agents.create_agent``.

    Captures the LLM, tools, and instructions *before* compilation so that
    Agentspan can translate the agent into a proper server-side workflow
    (AI_MODEL task for the LLM + SIMPLE tasks for each tool), matching the
    OpenAI/ADK integration pattern.

    Args:
        model: A LangChain chat model (e.g. ``ChatOpenAI``) or model string.
        tools: List of ``@tool``-decorated callables or ``StructuredTool`` instances.
        name: Agent name registered with Conductor.
        system_prompt: System prompt string or a LangChain ``SystemMessage``
            used as the agent's instructions.
        **kwargs: Forwarded to ``langchain.agents.create_agent``.

    Returns:
        A ``CompiledStateGraph`` with ``._agentspan_meta`` attached for
        proper Agentspan serialization.
    """
    from langchain.agents import create_agent as _lc_create_agent  # type: ignore[import]

    resolved_tools = tools or []
    graph = _lc_create_agent(
        model,
        tools=resolved_tools,
        name=name,
        system_prompt=system_prompt,
        **kwargs,
    )

    # Attach metadata — serializer uses this for full extraction
    instructions: Optional[str] = None
    if isinstance(system_prompt, str):
        instructions = system_prompt
    elif system_prompt is not None:
        # SystemMessage / BaseMessage
        try:
            instructions = str(system_prompt.content)
        except AttributeError:
            pass

    graph._agentspan_meta = {
        "llm": model,
        "tools": resolved_tools,
        "instructions": instructions,
    }

    return graph
