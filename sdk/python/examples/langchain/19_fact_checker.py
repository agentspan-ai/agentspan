# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Fact Checker — agent that verifies factual claims against a knowledge base.

Demonstrates:
    - Looking up claims against a curated fact database
    - Distinguishing between verified, unverified, and false claims
    - Providing sources and confidence scores
    - Practical use case: automated misinformation detection assistant

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Fact database ─────────────────────────────────────────────────────────────

FACT_DB = {
    "python_created": {
        "claim": "Python was created by Guido van Rossum",
        "verdict": "TRUE",
        "detail": "Python was created by Guido van Rossum and first released in 1991.",
        "source": "Python official history (python.org)",
        "confidence": 0.99,
    },
    "python_year": {
        "claim": "Python was first released in 1991",
        "verdict": "TRUE",
        "detail": "Python 0.9.0 was released in February 1991.",
        "source": "Python official history (python.org)",
        "confidence": 0.98,
    },
    "earth_sun_distance": {
        "claim": "The Earth is approximately 93 million miles from the Sun",
        "verdict": "TRUE",
        "detail": "Average Earth-Sun distance is ~93 million miles (150 million km), also known as 1 AU.",
        "source": "NASA Solar System Exploration",
        "confidence": 0.99,
    },
    "water_formula": {
        "claim": "Water has the chemical formula H2O",
        "verdict": "TRUE",
        "detail": "Water consists of two hydrogen atoms and one oxygen atom.",
        "source": "Standard chemistry reference",
        "confidence": 1.0,
    },
    "shakespeare_hamlet": {
        "claim": "Shakespeare wrote Hamlet",
        "verdict": "TRUE",
        "detail": "Hamlet was written by William Shakespeare around 1600-1601.",
        "source": "Encyclopaedia Britannica",
        "confidence": 0.99,
    },
    "great_wall_visible": {
        "claim": "The Great Wall of China is visible from space with the naked eye",
        "verdict": "FALSE",
        "detail": "This is a common myth. Astronauts and NASA have confirmed the Great Wall cannot be seen from space without aid.",
        "source": "NASA, Chinese astronaut Yang Liwei (2003)",
        "confidence": 0.97,
    },
    "lightning_twice": {
        "claim": "Lightning never strikes the same place twice",
        "verdict": "FALSE",
        "detail": "Lightning frequently strikes the same location multiple times. The Empire State Building is struck ~20-25 times per year.",
        "source": "NOAA Lightning Safety Program",
        "confidence": 0.99,
    },
}


@tool
def look_up_fact(claim: str) -> str:
    """Look up a specific claim in the fact verification database.

    Searches by keywords from the claim and returns matching verified facts.

    Args:
        claim: The specific claim to verify (e.g., 'Python was created in 1991').
    """
    claim_lower = claim.lower()
    matches = []
    for key, fact in FACT_DB.items():
        fact_words = set(fact["claim"].lower().split())
        claim_words = set(claim_lower.split())
        overlap = len(fact_words & claim_words)
        if overlap >= 3:
            matches.append((overlap, fact))

    if not matches:
        return f"No matching facts found for: '{claim}'. Cannot verify with current knowledge base."

    matches.sort(key=lambda x: -x[0])
    fact = matches[0][1]
    return (
        f"Verdict: {fact['verdict']}\n"
        f"Claim matched: {fact['claim']}\n"
        f"Details: {fact['detail']}\n"
        f"Source: {fact['source']}\n"
        f"Confidence: {fact['confidence'] * 100:.0f}%"
    )


@tool
def check_multiple_claims(claims: str) -> str:
    """Verify multiple claims at once.

    Args:
        claims: Newline-separated or pipe-separated list of claims to check.
    """
    # Split by newline or pipe
    if "|" in claims:
        claim_list = [c.strip() for c in claims.split("|") if c.strip()]
    else:
        claim_list = [c.strip() for c in claims.split("\n") if c.strip()]

    results = []
    for i, claim in enumerate(claim_list, 1):
        result = look_up_fact.invoke({"claim": claim})
        results.append(f"Claim {i}: \"{claim}\"\n{result}")

    return "\n\n".join(results)


@tool
def assess_claim_plausibility(claim: str) -> str:
    """Use LLM reasoning to assess the plausibility of a claim that isn't in the database.

    Args:
        claim: The claim to assess for plausibility.
    """
    response = llm.invoke(
        f"Assess the factual plausibility of this claim: '{claim}'\n\n"
        f"Consider: Is this consistent with established science/history/facts? "
        f"Rate confidence as: HIGH, MEDIUM, or LOW. "
        f"Provide a brief assessment (2-3 sentences) and note any important caveats."
    )
    return f"[Plausibility Assessment]\n{response.content.strip()}\n(Note: This is LLM reasoning, not verified data)"


FACT_CHECKER_SYSTEM = """You are a rigorous fact-checking assistant.
When checking facts:
1. Always look up specific claims in the database first
2. For multiple claims, use check_multiple_claims for efficiency
3. If a claim is not in the database, use plausibility assessment with a clear disclaimer
4. Give a clear final verdict: VERIFIED TRUE / VERIFIED FALSE / UNVERIFIED
5. Always cite your sources
"""

graph = create_agent(
    llm,
    tools=[look_up_fact, check_multiple_claims, assess_claim_plausibility],
    name="fact_checker_agent",
    system_prompt=FACT_CHECKER_SYSTEM,
)

if __name__ == "__main__":
    claims_to_check = [
        "Python was created by Guido van Rossum and first released in 1991.",
        "The Great Wall of China is visible from space with the naked eye.",
        "Lightning never strikes the same place twice.",
    ]

    with AgentRuntime() as runtime:
        for claim in claims_to_check:
            print(f"\nChecking: {claim}")
            result = runtime.run(graph, f"Please fact-check this claim: {claim}")
            result.print_result()
            print("-" * 60)
