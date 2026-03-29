# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent Tool — wrap an agent as a callable tool.

Unlike sub-agents (which use handoff delegation), an agent_tool is invoked
inline by the parent LLM like a function call. The child agent runs its
own workflow and returns the result as a tool output.

    manager (parent)
      tools:
        - agent_tool(researcher)   <- child agent with search tool
        - calculate                <- regular tool

Requirements:
    - Conductor server with AgentTool support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, agent_tool, tool
from settings import settings


# ── Child agent's tool ─────────────────────────────────────────────
@tool
def search_knowledge_base(query: str) -> dict:
    """Search an internal knowledge base for information.

    Args:
        query: The search query.

    Returns:
        Dictionary with search results.
    """
    data = {
        "python": {
            "summary": "Python is a high-level programming language.",
            "use_cases": ["web development", "data science", "automation"],
        },
        "rust": {
            "summary": "Rust is a systems language focused on safety and performance.",
            "use_cases": ["systems programming", "WebAssembly", "CLI tools"],
        },
    }
    for key, val in data.items():
        if key in query.lower():
            return {"query": query, **val}
    return {"query": query, "summary": "No specific data found."}


# ── Regular tool for parent ────────────────────────────────────────
@tool
def calculate(expression: str) -> dict:
    """Evaluate a math expression safely.

    Args:
        expression: A mathematical expression to evaluate.

    Returns:
        Dictionary with the result.
    """
    allowed = set("0123456789+-*/.(). ")
    if not all(c in allowed for c in expression):
        return {"error": "Invalid expression"}
    try:
        return {"result": eval(expression)}
    except Exception as e:
        return {"error": str(e)}


# ── Child agent (has its own tools) ────────────────────────────────
researcher = Agent(
    name="researcher_45",
    model=settings.llm_model,
    instructions=(
        "You are a research assistant. Use search_knowledge_base to find "
        "information about topics. Provide concise summaries."
    ),
    tools=[search_knowledge_base],
)

# ── Parent agent (uses researcher as a tool) ───────────────────────
manager = Agent(
    name="manager_45",
    model=settings.llm_model,
    instructions=(
        "You are a project manager. Use the researcher tool to gather "
        "information and the calculate tool for math. Synthesize findings."
    ),
    tools=[agent_tool(researcher), calculate],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.45_agent_tool
        runtime.deploy(manager)
        runtime.serve(manager)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        #     manager,
        #     "Research Python and Rust, then calculate how many use cases they "
        #     "have combined.",
        # )
        # result.print_result()

