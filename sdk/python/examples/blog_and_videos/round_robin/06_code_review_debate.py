"""Code Review Debate — Round Robin Strategy

Three reviewers take turns critiquing and improving a code snippet.
Each round, every reviewer sees what the others said and builds on it.
After the debate, a summarizer produces the final verdict.

Setup:
    pip install agentspan
    agentspan server start

    python 06_code_review_debate.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from settings import settings

from agentspan.agents import Agent, AgentRuntime, Strategy


# ── Reviewers ────────────────────────────────────────────────────────

architect = Agent(
    name="architect",
    model=settings.llm_model,
    instructions=(
        "You are a software architect reviewing code. Focus on:\n"
        "- Design patterns and structure\n"
        "- Separation of concerns\n"
        "- Scalability and maintainability\n\n"
        "Read what other reviewers said before you. Build on their points, "
        "don't repeat them. Keep your response to 2-3 paragraphs."
    ),
)

security_reviewer = Agent(
    name="security_reviewer",
    model=settings.llm_model,
    instructions=(
        "You are a security engineer reviewing code. Focus on:\n"
        "- Injection vulnerabilities (SQL, command, path traversal)\n"
        "- Authentication and authorization gaps\n"
        "- Data exposure and insecure defaults\n\n"
        "Read what other reviewers said before you. Build on their points, "
        "don't repeat them. Keep your response to 2-3 paragraphs."
    ),
)

pragmatist = Agent(
    name="pragmatist",
    model=settings.llm_model,
    instructions=(
        "You are a senior engineer who values shipping. Focus on:\n"
        "- Is this good enough to merge today?\n"
        "- What is the minimum fix needed?\n"
        "- What can wait for a follow-up PR?\n\n"
        "Push back on over-engineering. Read what other reviewers said "
        "and decide what actually matters for this PR. "
        "Keep your response to 2-3 paragraphs."
    ),
)

summarizer = Agent(
    name="summarizer",
    model=settings.llm_model,
    instructions=(
        "You observed a code review discussion between an architect, "
        "a security reviewer, and a pragmatist. Produce a final verdict:\n\n"
        "1. APPROVE, REQUEST CHANGES, or NEEDS DISCUSSION\n"
        "2. Must-fix items (block merge)\n"
        "3. Nice-to-have items (follow-up PR)\n"
        "4. One-sentence summary\n\n"
        "Be decisive. Don't hedge."
    ),
)

# ── Round Robin: 6 turns (2 rounds of 3 reviewers) ─────────────────

review = Agent(
    name="code_review_round_robin",
    model=settings.llm_model,
    agents=[architect, security_reviewer, pragmatist],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=6,
)

pipeline = review >> summarizer


if __name__ == "__main__":
    code = """\
Review this code:

import sqlite3
import os

def get_user(db_path, user_id):
    conn = sqlite3.connect(db_path)
    query = f"SELECT * FROM users WHERE id = {user_id}"
    result = conn.execute(query).fetchone()
    conn.close()
    return result

def save_upload(filename, data):
    path = f"/uploads/{filename}"
    with open(path, "wb") as f:
        f.write(data)
    os.chmod(path, 0o777)
    return path

def process_payment(amount, card_number):
    print(f"Processing ${amount} on card {card_number}")
    return {"status": "ok", "amount": amount}
"""

    with AgentRuntime() as runtime:
        result = runtime.run(pipeline, code)
        result.print_result()
