# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Fact Checker — agent that verifies claims against a knowledge base.

Demonstrates:
    - Claim parsing and verification tools
    - Source lookup with confidence scoring
    - Structured fact-checking workflow

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


KNOWLEDGE_BASE = {
    "great wall of china visible from space": {
        "verdict": "FALSE",
        "explanation": "The Great Wall is too narrow (~5m) to be seen from space with the naked eye. This is a popular myth debunked by astronauts.",
        "confidence": 0.99,
        "source": "NASA, Chinese astronaut Yang Liwei (2003)",
    },
    "humans use 10% of brain": {
        "verdict": "FALSE",
        "explanation": "Neuroimaging shows virtually all brain regions are active. The 10% myth has no scientific basis.",
        "confidence": 0.99,
        "source": "Journal of Neuroscience, Barry Beyerstein (1999)",
    },
    "lightning never strikes twice": {
        "verdict": "FALSE",
        "explanation": "Lightning frequently strikes the same spot multiple times. The Empire State Building is struck ~20-25 times per year.",
        "confidence": 0.99,
        "source": "NOAA Lightning Safety Program",
    },
    "water conducts electricity": {
        "verdict": "NUANCED",
        "explanation": "Pure distilled water is a poor conductor. Tap water conducts electricity due to dissolved salts and minerals.",
        "confidence": 0.95,
        "source": "Standard chemistry reference",
    },
    "python is compiled language": {
        "verdict": "NUANCED",
        "explanation": "Python compiles to bytecode (.pyc) but is generally considered an interpreted language due to runtime execution.",
        "confidence": 0.90,
        "source": "Python documentation",
    },
}


@tool
def check_claim(claim: str) -> str:
    """Look up a claim in the fact-checking knowledge base.

    Args:
        claim: The factual claim to verify.
    """
    claim_lower = claim.lower()
    for key, data in KNOWLEDGE_BASE.items():
        if any(word in claim_lower for word in key.split()):
            return (
                f"Verdict: {data['verdict']}\n"
                f"Explanation: {data['explanation']}\n"
                f"Confidence: {data['confidence']*100:.0f}%\n"
                f"Source: {data['source']}"
            )
    return f"No entry found for this claim. Unable to verify: '{claim[:80]}'"


@tool
def extract_claims(text: str) -> str:
    """Extract individual factual claims from a block of text.

    Args:
        text: Text that may contain multiple factual claims.
    """
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if len(s.strip()) > 15]
    claim_indicators = ["is", "are", "was", "were", "never", "always", "only", "can", "cannot", "has", "have"]
    claims = []
    for sentence in sentences:
        if any(f" {ind} " in f" {sentence.lower()} " for ind in claim_indicators):
            claims.append(sentence)
    if not claims:
        return "No distinct factual claims extracted."
    return f"Extracted {len(claims)} claim(s):\n" + "\n".join(f"{i+1}. {c}." for i, c in enumerate(claims[:5]))


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [check_claim, extract_claims]

graph = create_agent(
    llm,
    tools=tools,
    name="fact_checker_agent",
    system_prompt=(
        "You are a rigorous fact-checker. Extract claims from text and verify them. "
        "Be precise about what is true, false, or nuanced. Always cite sources when available."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Fact-check these claims: 'You can see the Great Wall of China from space' and 'humans only use 10% of their brain'.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.19_fact_checker
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
