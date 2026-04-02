# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Research Agent — create_agent with search, summarize, and cite_source tools.

Demonstrates:
    - Combining search, summarization, and citation tools in one agent
    - Mock implementations that return realistic research-style data
    - Building a multi-step research workflow via tool chaining

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agentspan.agents import AgentRuntime

# Mock research database
_MOCK_SEARCH_RESULTS = {
    "climate change": [
        "Global temperatures have risen ~1.1°C since pre-industrial times (IPCC, 2023).",
        "Sea levels are rising at 3.7 mm/year due to thermal expansion and ice melt.",
        "Extreme weather events have increased in frequency and intensity since 1980.",
    ],
    "artificial intelligence": [
        "Large language models (LLMs) have achieved human-level performance on many benchmarks.",
        "The global AI market is projected to reach $1.8 trillion by 2030.",
        "AI ethics and alignment remain active research challenges.",
    ],
    "renewable energy": [
        "Solar PV costs have dropped 89% in the past decade.",
        "Wind power capacity exceeded 900 GW globally in 2023.",
        "Battery storage is the key bottleneck for 100% renewable grids.",
    ],
}


@tool
def search(query: str) -> str:
    """Search for information on a topic and return a list of findings.

    Uses a mock database for demonstration. Returns relevant facts.
    """
    query_lower = query.lower()
    for key, results in _MOCK_SEARCH_RESULTS.items():
        if key in query_lower:
            return "\n".join(f"- {r}" for r in results)
    return f"No specific results found for '{query}'. Try a broader search term."


@tool
def summarize(text: str, max_sentences: int = 3) -> str:
    """Summarize the provided text into at most max_sentences sentences.

    This is a mock that truncates content for demonstration purposes.
    """
    sentences = [s.strip() for s in text.replace("\n", ". ").split(". ") if s.strip()]
    selected = sentences[:max_sentences]
    return " ".join(selected) + ("." if selected and not selected[-1].endswith(".") else "")


@tool
def cite_source(claim: str, source_type: str = "academic") -> str:
    """Generate a formatted citation for a given claim.

    Args:
        claim: The statement that needs to be cited.
        source_type: One of 'academic', 'news', or 'report'.

    Returns a mock citation in APA format.
    """
    citations = {
        "academic": "Smith, J., & Doe, A. (2024). Research findings on the topic. Journal of Science, 12(3), 45–67.",
        "news": "Reuters. (2024, January 15). New developments in research. Reuters.com.",
        "report": "World Economic Forum. (2024). Global Report 2024. WEF Publications.",
    }
    source = citations.get(source_type, citations["academic"])
    return f"Claim: '{claim[:80]}...'\nCitation: {source}"


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(
    llm,
    tools=[search, summarize, cite_source],
    system_prompt=(
        "You are a research assistant. For any research question: "
        "1) search for relevant information, "
        "2) summarize the findings, "
        "3) provide citations. "
        "Be thorough and cite your sources."
    ),
    name="research_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        graph,
        "What are the latest developments in climate change research? Include sources.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.10_research_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
