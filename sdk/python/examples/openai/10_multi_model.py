# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agent — Multi-Model Handoff with different LLMs.

Demonstrates:
    - Different agents using different models
    - Handoffs between agents with different capabilities
    - Model override for cost/performance optimization

Requirements:
    - pip install openai-agents
    - Conductor server with OpenAI LLM integrations configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
    - AGENT_SECONDARY_LLM_MODEL=openai/gpt-4o in .env or environment
"""

from agents import Agent, ModelSettings, function_tool

from agentspan.agents import AgentRuntime

from settings import settings


@function_tool
def search_docs(query: str) -> str:
    """Search the documentation for relevant information."""
    docs = {
        "authentication": "Use OAuth 2.0 with JWT tokens. See /auth/login endpoint.",
        "rate limiting": "100 requests/minute per API key. 429 status on exceeded.",
        "pagination": "Use cursor-based pagination with ?cursor=xxx&limit=50.",
        "webhooks": "POST to /webhooks/register with event types and callback URL.",
    }
    for key, value in docs.items():
        if key in query.lower():
            return value
    return "No documentation found. Try rephrasing your query."


@function_tool
def generate_code_sample(language: str, topic: str) -> str:
    """Generate a code sample for a given topic."""
    samples = {
        ("python", "authentication"): (
            "import requests\n"
            "resp = requests.post('/auth/login', json={'key': 'API_KEY'})\n"
            "token = resp.json()['token']"
        ),
        ("javascript", "authentication"): (
            "const resp = await fetch('/auth/login', {\n"
            "  method: 'POST',\n"
            "  body: JSON.stringify({ key: 'API_KEY' })\n"
            "});\n"
            "const { token } = await resp.json();"
        ),
    }
    return samples.get(
        (language.lower(), topic.lower()),
        f"// Sample for {topic} in {language}\n// (template not available)",
    )


# Fast, cheap model for initial triage
triage = Agent(
    name="triage",
    instructions=(
        "You are a documentation triage agent. Determine what the user needs "
        "and hand off to the appropriate specialist:\n"
        "- For documentation lookups → doc_specialist\n"
        "- For code examples → code_specialist\n"
        "Keep your response to one sentence before handing off."
    ),
    model=settings.llm_model,
    model_settings=ModelSettings(temperature=0.1),
    handoffs=[],  # populated below
)

# Knowledgeable model for doc lookups
doc_specialist = Agent(
    name="doc_specialist",
    instructions=(
        "You are a documentation specialist. Search the docs and provide "
        "clear, well-structured answers. Include relevant links and examples."
    ),
    model=settings.secondary_llm_model,
    tools=[search_docs],
    model_settings=ModelSettings(temperature=0.2, max_tokens=500),
)

# Code-focused model for code generation
code_specialist = Agent(
    name="code_specialist",
    instructions=(
        "You are a code example specialist. Generate clean, well-commented "
        "code samples. Always specify the language and include error handling."
    ),
    model=settings.secondary_llm_model,
    tools=[generate_code_sample],
    model_settings=ModelSettings(temperature=0.3, max_tokens=800),
)

# Wire up handoffs
triage.handoffs = [doc_specialist, code_specialist]

with AgentRuntime() as runtime:
    result = runtime.run(
        triage,
        "I need a Python code example for authenticating with the API.",
    )
    result.print_result()
