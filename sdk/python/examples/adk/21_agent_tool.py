# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK AgentTool — agent-as-tool invocation.

Demonstrates:
    - Using AgentTool to wrap an agent as a callable tool
    - The parent agent's LLM invokes the child agent like a function
    - The child agent runs its own tools and returns the result
    - Unlike sub_agents (handoff), AgentTool runs inline and returns

Architecture:
    manager (parent agent)
      tools:
        - AgentTool(researcher)   <- child agent with its own tools
        - AgentTool(calculator)   <- another child agent

Requirements:
    - pip install google-adk
    - Conductor server with AgentTool support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
"""

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from agentspan.agents import AgentRuntime


# ── Child agents (each has their own tools) ──────────────────────

def search_knowledge_base(query: str) -> dict:
    """Search an internal knowledge base for information.

    Args:
        query: The search query.

    Returns:
        Dictionary with search results.
    """
    data = {
        "python": {
            "summary": "Python is a high-level programming language created by Guido van Rossum in 1991.",
            "popularity": "Most popular language on TIOBE index (2024)",
            "key_use_cases": ["web development", "data science", "AI/ML", "automation"],
        },
        "rust": {
            "summary": "Rust is a systems programming language focused on safety and performance.",
            "popularity": "Most admired language on Stack Overflow survey (2024)",
            "key_use_cases": ["systems programming", "WebAssembly", "CLI tools", "embedded"],
        },
    }
    for key, val in data.items():
        if key in query.lower():
            return {"query": query, "found": True, **val}
    return {"query": query, "found": False, "summary": "No results found."}


researcher = Agent(
    name="researcher",
    model=settings.llm_model,
    instruction=(
        "You are a research assistant. Use the knowledge base tool to find "
        "information and provide concise, factual answers."
    ),
    tools=[search_knowledge_base],
)


def compute(expression: str) -> dict:
    """Evaluate a mathematical expression.

    Args:
        expression: A math expression like '2 + 3 * 4'.

    Returns:
        Dictionary with the result.
    """
    import math

from settings import settings
    safe = {"abs": abs, "round": round, "min": min, "max": max,
            "sqrt": math.sqrt, "pow": pow, "pi": math.pi, "e": math.e}
    try:
        result = eval(expression, {"__builtins__": {}}, safe)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


calculator = Agent(
    name="calculator",
    model=settings.llm_model,
    instruction="You are a math assistant. Use the compute tool for calculations.",
    tools=[compute],
)


# ── Parent agent with AgentTool wrappers ─────────────────────────

manager = Agent(
    name="manager",
    model=settings.llm_model,
    instruction=(
        "You are a manager agent. You have two specialist agents available as tools:\n"
        "- researcher: for looking up information\n"
        "- calculator: for math computations\n\n"
        "Use the appropriate agent tool to answer the user's question. "
        "You can call multiple agent tools if needed."
    ),
    tools=[
        AgentTool(agent=researcher),
        AgentTool(agent=calculator),
    ],
)

with AgentRuntime() as runtime:
    result = runtime.run(
        manager,
        "Look up information about Python and Rust, then calculate "
        "what percentage of Python's 4 key use cases overlap with Rust's 4 use cases.",
    )
    result.print_result()
