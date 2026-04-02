# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Agent with Streaming — real-time event streaming.

Demonstrates:
    - Streaming events from a Google ADK agent running on Conductor
    - The runtime.stream() method works identically for foreign agents
    - Events include: thinking, tool_call, tool_result, done

Requirements:
    - pip install google-adk
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def search_documentation(query: str) -> dict:
    """Search the product documentation.

    Args:
        query: Search query string.

    Returns:
        Dictionary with matching documentation sections.
    """
    docs = {
        "installation": {
            "title": "Installation Guide",
            "content": "Run `pip install mypackage`. Requires Python 3.9+.",
        },
        "authentication": {
            "title": "Authentication",
            "content": "Use API keys via the X-API-Key header. Keys are managed in the dashboard.",
        },
        "rate limits": {
            "title": "Rate Limiting",
            "content": "Free tier: 100 req/min. Pro: 1000 req/min. Enterprise: unlimited.",
        },
    }
    for key, value in docs.items():
        if key in query.lower():
            return {"found": True, **value}
    return {"found": False, "message": "No matching documentation found."}


agent = Agent(
    name="docs_assistant",
    model=settings.llm_model,
    instruction=(
        "You are a documentation assistant. Use the search tool to find "
        "relevant docs and provide clear, well-formatted answers."
    ),
    tools=[search_documentation],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "How do I authenticate with the API?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.adk.06_streaming
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

        # Streaming alternative:
        # print("Streaming events:\n")
        # for event in runtime.stream(agent, "How do I authenticate with the API?"):
        #     print(f"  [{event.type}] {event.data}")
        # print("\nStream complete.")
