# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Recommendation Agent — personalized recommendations based on user preferences.

Demonstrates:
    - User profile-aware recommendation engine
    - Filtering and ranking candidate items by preference match
    - Explanation-driven recommendations with reasoning
    - Practical use case: personalized product or content recommendation

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
from typing import List

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Mock catalog ──────────────────────────────────────────────────────────────

BOOKS = [
    {"id": "b1", "title": "Clean Code", "author": "Robert C. Martin", "genre": "programming", "level": "intermediate", "rating": 4.7},
    {"id": "b2", "title": "The Pragmatic Programmer", "author": "Hunt & Thomas", "genre": "programming", "level": "intermediate", "rating": 4.8},
    {"id": "b3", "title": "Designing Data-Intensive Applications", "author": "Martin Kleppmann", "genre": "data engineering", "level": "advanced", "rating": 4.9},
    {"id": "b4", "title": "Python Crash Course", "author": "Eric Matthes", "genre": "programming", "level": "beginner", "rating": 4.6},
    {"id": "b5", "title": "The Algorithm Design Manual", "author": "Steven Skiena", "genre": "algorithms", "level": "advanced", "rating": 4.5},
    {"id": "b6", "title": "Atomic Habits", "author": "James Clear", "genre": "productivity", "level": "all", "rating": 4.8},
    {"id": "b7", "title": "Deep Learning", "author": "Goodfellow et al.", "genre": "machine learning", "level": "advanced", "rating": 4.7},
    {"id": "b8", "title": "Hands-On Machine Learning", "author": "Aurélien Géron", "genre": "machine learning", "level": "intermediate", "rating": 4.8},
]

COURSES = [
    {"id": "c1", "title": "LangChain for LLM Applications", "provider": "DeepLearning.AI", "level": "intermediate", "hours": 4},
    {"id": "c2", "title": "Machine Learning Specialization", "provider": "Coursera", "level": "beginner", "hours": 90},
    {"id": "c3", "title": "Advanced Python Programming", "provider": "Udemy", "level": "intermediate", "hours": 20},
    {"id": "c4", "title": "System Design Interview", "provider": "Educative", "level": "advanced", "hours": 15},
    {"id": "c5", "title": "Data Engineering with Python", "provider": "DataCamp", "level": "intermediate", "hours": 30},
]


@tool
def get_book_recommendations(
    interests: str,
    skill_level: str = "intermediate",
    max_results: int = 3,
) -> str:
    """Get personalized book recommendations based on interests and skill level.

    Args:
        interests: Comma-separated list of interests (e.g., 'programming, machine learning').
        skill_level: Reader's level — 'beginner', 'intermediate', 'advanced'.
        max_results: Number of books to recommend (1-5).
    """
    interest_list = [i.strip().lower() for i in interests.split(",")]
    candidates = []
    for book in BOOKS:
        genre_match = any(i in book["genre"] or book["genre"] in i for i in interest_list)
        level_match = book["level"] in (skill_level, "all")
        if genre_match or level_match:
            score = (1 if genre_match else 0) + (1 if level_match else 0) + book["rating"] / 5
            candidates.append((score, book))

    candidates.sort(key=lambda x: -x[0])
    top = candidates[:max_results]

    if not top:
        return "No matching books found. Try broader interests."

    lines = [f"Top {len(top)} book recommendations:"]
    for _, book in top:
        lines.append(
            f"  📚 '{book['title']}' by {book['author']} "
            f"[{book['genre']}, {book['level']}, ★{book['rating']}]"
        )
    return "\n".join(lines)


@tool
def get_course_recommendations(
    learning_goal: str,
    available_hours: int = 20,
) -> str:
    """Get online course recommendations based on a learning goal and time budget.

    Args:
        learning_goal: What you want to learn (e.g., 'build LLM apps', 'machine learning').
        available_hours: Total hours available to dedicate (1-100).
    """
    goal_lower = learning_goal.lower()
    candidates = []
    for course in COURSES:
        title_match = any(w in course["title"].lower() for w in goal_lower.split())
        time_match = course["hours"] <= available_hours * 1.2
        if title_match or time_match:
            fit_score = (1 if title_match else 0) + (1 if time_match else 0)
            candidates.append((fit_score, course))

    candidates.sort(key=lambda x: (-x[0], x[1]["hours"]))
    top = candidates[:3]

    if not top:
        return "No matching courses found."

    lines = [f"Course recommendations for '{learning_goal}':"]
    for _, c in top:
        lines.append(
            f"  🎓 '{c['title']}' ({c['provider']}) — {c['hours']}h, {c['level']}"
        )
    return "\n".join(lines)


@tool
def explain_recommendation(item_title: str, user_interests: str) -> str:
    """Generate a personalized explanation for why an item is recommended.

    Args:
        item_title: Title of the book or course being recommended.
        user_interests: User's stated interests and goals.
    """
    response = llm.invoke(
        f"Explain why '{item_title}' is a great recommendation for someone interested in: {user_interests}. "
        f"Be specific and compelling. 2-3 sentences."
    )
    return f"Why '{item_title}': {response.content.strip()}"


RECOMMENDER_SYSTEM = """You are a personalized learning advisor.
When making recommendations:
1. Get book recommendations tailored to their interests and level
2. Suggest relevant courses based on their goal and time budget
3. Provide personalized explanations for top picks
4. Create a structured learning path recommendation
"""

graph = create_agent(
    llm,
    tools=[get_book_recommendations, get_course_recommendations, explain_recommendation],
    name="recommendation_agent",
    system_prompt=RECOMMENDER_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "I'm an intermediate Python developer who wants to learn machine learning and LLM development. "
            "I have about 30 hours available. What should I read and study?",
        )
        print(f"Status: {result.status}")
        result.print_result()
