# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Classification Agent — text classifier with keyword-based and LLM-based routing.

Demonstrates:
    - Rule-based text classification tools
    - Confidence-scored category assignment
    - Multi-label classification

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

TOPIC_KEYWORDS = {
    "Technology": ["software", "hardware", "ai", "algorithm", "code", "computer", "data", "cloud", "api", "digital"],
    "Sports": ["game", "player", "team", "score", "match", "tournament", "championship", "athlete", "goal", "win"],
    "Finance": ["market", "stock", "invest", "revenue", "profit", "bank", "fund", "dividend", "budget", "economy"],
    "Health": ["medical", "health", "doctor", "treatment", "disease", "patient", "drug", "hospital", "symptoms", "care"],
    "Science": ["research", "experiment", "study", "discovery", "particle", "quantum", "biology", "chemistry", "lab"],
    "Politics": ["government", "election", "policy", "senator", "president", "vote", "party", "congress", "legislation"],
}

INTENT_KEYWORDS = {
    "Question": ["what", "how", "why", "when", "where", "who", "which", "?"],
    "Request": ["please", "can you", "could you", "help me", "i need", "i want"],
    "Complaint": ["problem", "issue", "broken", "not working", "failed", "error", "wrong", "bad"],
    "Feedback": ["suggest", "recommend", "think", "believe", "opinion", "feedback", "idea"],
}


@tool
def classify_topic(text: str) -> str:
    """Classify text into one or more topic categories.

    Args:
        text: The text to classify.
    """
    text_lower = text.lower()
    scores = {}
    for category, keywords in TOPIC_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            scores[category] = count

    if not scores:
        return "Category: General/Other (no strong topic signals detected)."

    total = sum(scores.values())
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    result = "Topic classification:\n"
    for cat, count in ranked[:3]:
        confidence = min(count / total * 100, 95)
        result += f"  • {cat}: {confidence:.0f}% confidence\n"
    return result.strip()


@tool
def classify_intent(text: str) -> str:
    """Detect the user's intent from the text.

    Args:
        text: The text to classify for intent.
    """
    text_lower = text.lower()
    detected = []
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            detected.append(intent)

    if not detected:
        return "Intent: Informational (statement or general content)."
    return f"Detected intent(s): {', '.join(detected)}"


@tool
def get_category_examples(category: str) -> str:
    """Return example texts that belong to a given category.

    Args:
        category: The category name (e.g., 'Technology', 'Sports').
    """
    examples = {
        "Technology": "Example: 'The new AI model achieved state-of-the-art performance on coding benchmarks.'",
        "Sports": "Example: 'The team won the championship after a thrilling overtime match.'",
        "Finance": "Example: 'Investors are concerned about rising interest rates affecting stock valuations.'",
        "Health": "Example: 'Researchers discovered a new treatment for reducing symptoms of the disease.'",
        "Science": "Example: 'The experiment confirmed quantum entanglement across 100km of fiber optic cable.'",
        "Politics": "Example: 'The senator proposed new legislation to address the issue of campaign finance.'",
    }
    return examples.get(category.title(), f"No examples stored for '{category}'.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [classify_topic, classify_intent, get_category_examples]

graph = create_agent(
    llm,
    tools=tools,
    name="classification_agent",
    system_prompt=(
        "You are a text classification assistant. Analyze text for topic and intent, "
        "provide confidence-scored categories, and explain your classifications."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Classify this text: 'How can I fix the broken API integration? The software keeps returning a 500 error and my team cannot deploy the code.'",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.22_classification_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
