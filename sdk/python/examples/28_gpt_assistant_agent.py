# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""GPTAssistantAgent — wrap OpenAI Assistants API as a Conductor agent.

Demonstrates ``GPTAssistantAgent`` which uses the OpenAI Assistants API
(with threads, runs, and built-in tools like code_interpreter) as a
Conductor agent.

Two modes:
    1. Use an existing assistant by ID
    2. Create a new assistant on-the-fly with model + instructions

Requirements:
    - pip install openai
    - Conductor server with LLM support
    - OPENAI_API_KEY=sk-... as environment variable
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import AgentRuntime
from agentspan.agents.ext import GPTAssistantAgent
from settings import settings

# ── Example 1: Create assistant on the fly ───────────────────────────

data_analyst = GPTAssistantAgent(
    name="data_analyst",
    model=settings.llm_model,
    instructions=(
        "You are a data analyst. Use the code interpreter to analyze data, "
        "create charts, and perform calculations."
    ),
    openai_tools=[{"type": "code_interpreter"}],
)

# ── Example 2: Use an existing assistant ─────────────────────────────

# If you already have an assistant created in the OpenAI dashboard:
# existing_assistant = GPTAssistantAgent(
#     name="my_assistant",
#     assistant_id="asst_abc123def456",
# )


if __name__ == "__main__":
    # ── Run ─────────────────────────────────────────────────────────────


    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.28_gpt_assistant_agent
        runtime.deploy(data_analyst)
        runtime.serve(data_analyst)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # print("--- GPT Assistant with Code Interpreter ---")
        # result = runtime.run(
        #     data_analyst,
        #     "Calculate the standard deviation of these numbers: 4, 8, 15, 16, 23, 42",
        # )
        # result.print_result()

