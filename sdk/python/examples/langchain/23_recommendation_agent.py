# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Recommendation Agent — content-based recommendation with scoring tools.

Demonstrates:
    - User preference matching against an item catalog
    - Scoring and ranking recommendations
    - Explaining why items are recommended

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

BOOK_CATALOG = [
    {"title": "Dune", "author": "Frank Herbert", "genre": ["sci-fi", "adventure"], "themes": ["politics", "ecology", "religion"], "difficulty": "medium"},
    {"title": "The Pragmatic Programmer", "author": "Hunt & Thomas", "genre": ["technical", "non-fiction"], "themes": ["software", "career", "coding"], "difficulty": "medium"},
    {"title": "Sapiens", "author": "Yuval Noah Harari", "genre": ["history", "non-fiction"], "themes": ["humanity", "society", "evolution"], "difficulty": "easy"},
    {"title": "Project Hail Mary", "author": "Andy Weir", "genre": ["sci-fi", "adventure"], "themes": ["science", "survival", "space"], "difficulty": "easy"},
    {"title": "Clean Code", "author": "Robert C. Martin", "genre": ["technical", "non-fiction"], "themes": ["software", "coding", "best practices"], "difficulty": "medium"},
    {"title": "The Name of the Wind", "author": "Patrick Rothfuss", "genre": ["fantasy", "adventure"], "themes": ["magic", "music", "coming-of-age"], "difficulty": "easy"},
    {"title": "Thinking, Fast and Slow", "author": "Daniel Kahneman", "genre": ["psychology", "non-fiction"], "themes": ["decision-making", "cognition", "behavior"], "difficulty": "medium"},
    {"title": "Neuromancer", "author": "William Gibson", "genre": ["sci-fi", "cyberpunk"], "themes": ["technology", "hacking", "corporate power"], "difficulty": "hard"},
]


@tool
def find_books_by_genre(genre: str) -> str:
    """Find books matching a genre keyword.

    Args:
        genre: The genre to search for (e.g., 'sci-fi', 'technical', 'fantasy').
    """
    matches = [b for b in BOOK_CATALOG if any(genre.lower() in g for g in b["genre"])]
    if not matches:
        return f"No books found for genre '{genre}'."
    return "\n".join(
        f"• {b['title']} by {b['author']} ({', '.join(b['genre'])}) — {b['difficulty']} difficulty"
        for b in matches
    )


@tool
def score_book_for_preferences(title: str, preferred_themes: str) -> str:
    """Score how well a book matches a user's preferred themes.

    Args:
        title: The book title to evaluate.
        preferred_themes: Comma-separated list of user's preferred themes.
    """
    book = next((b for b in BOOK_CATALOG if b["title"].lower() == title.lower()), None)
    if not book:
        return f"Book '{title}' not found in catalog."

    prefs = [p.strip().lower() for p in preferred_themes.split(",")]
    matches = [t for t in book["themes"] if any(p in t for p in prefs)]
    score = len(matches) / max(len(prefs), 1) * 10

    return (
        f"Book: '{book['title']}'\n"
        f"Matching themes: {', '.join(matches) if matches else 'none'}\n"
        f"Recommendation score: {score:.1f}/10\n"
        f"Difficulty: {book['difficulty']}"
    )


@tool
def get_similar_books(title: str) -> str:
    """Find books similar to a given title based on shared genres and themes.

    Args:
        title: The reference book title.
    """
    source = next((b for b in BOOK_CATALOG if b["title"].lower() == title.lower()), None)
    if not source:
        return f"Book '{title}' not found in catalog."

    similarities = []
    for book in BOOK_CATALOG:
        if book["title"] == source["title"]:
            continue
        genre_overlap = len(set(source["genre"]) & set(book["genre"]))
        theme_overlap = len(set(source["themes"]) & set(book["themes"]))
        if genre_overlap + theme_overlap > 0:
            similarities.append((book, genre_overlap + theme_overlap))

    if not similarities:
        return f"No similar books found for '{title}'."

    similarities.sort(key=lambda x: -x[1])
    result = f"Books similar to '{source['title']}':\n"
    for book, score in similarities[:3]:
        result += f"  • {book['title']} by {book['author']} (similarity: {score})\n"
    return result.strip()


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [find_books_by_genre, score_book_for_preferences, get_similar_books]

graph = create_agent(
    llm,
    tools=tools,
    name="recommendation_agent",
    system_prompt=(
        "You are a personalized book recommendation assistant. Use tools to find, score, "
        "and explain book recommendations based on the user's preferences."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "I love science fiction and I'm interested in themes of technology and survival. "
            "Recommend a book and find something similar to 'Dune'.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.23_recommendation_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
