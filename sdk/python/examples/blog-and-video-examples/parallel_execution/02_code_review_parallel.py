import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

"""Parallel Code Review — Bug Reviewer | Security Reviewer | Style Reviewer

Three agents review the same code simultaneously, each looking for
different issues. Results arrive together.

Demonstrates:
    - Parallel strategy with Strategy.PARALLEL
    - AgentRuntime for durable execution
    - sub_results for per-agent outputs

Setup:
    pip install agentspan
    agentspan server start
    python 02_code_review_parallel.py
"""

from agentspan.agents import Agent, AgentRuntime, Strategy


# ── Agents ────────────────────────────────────────────────────────

bug_reviewer = Agent(
    name="bug_reviewer",
    model="openai/gpt-4o",
    instructions=(
        "You are a senior software engineer reviewing code for bugs. "
        "Read the ACTUAL code carefully. Only report issues you can "
        "point to in specific lines. Quote the exact code and explain "
        "what's wrong.\n\n"
        "Look for: logic errors, unhandled edge cases, crashes, and "
        "incorrect behavior.\n\n"
        "If the code has no bugs, say 'No bugs found.' "
        "Do NOT invent issues. Do NOT give generic advice."
    ),
)

security_reviewer = Agent(
    name="security_reviewer",
    model="openai/gpt-4o",
    instructions=(
        "You are an application security engineer reviewing code for "
        "vulnerabilities. Read the ACTUAL code carefully. Only report "
        "vulnerabilities you can point to in specific lines.\n\n"
        "Look for: injection flaws, insecure defaults, data exposure, "
        "missing input validation, OWASP Top 10 issues. Rate each "
        "finding as Critical, High, Medium, or Low.\n\n"
        "If the code has no security issues, say 'No security issues "
        "found.' Do NOT invent vulnerabilities. Do NOT give generic "
        "security advice."
    ),
)

style_reviewer = Agent(
    name="style_reviewer",
    model="openai/gpt-4o",
    instructions=(
        "You are a Python code quality reviewer. Read the ACTUAL code "
        "carefully. Only report style issues you can point to in "
        "specific lines.\n\n"
        "Look for: missing type hints, missing docstrings, hardcoded "
        "values, print vs logging, naming issues, readability.\n\n"
        "If the code style is good, say 'Code style looks good.' "
        "Do NOT invent issues. Do NOT give generic advice."
    ),
)

# ── Parallel Review ──────────────────────────────────────────────

review = Agent(
    name="code_review",
    model="openai/gpt-4o",
    agents=[bug_reviewer, security_reviewer, style_reviewer],
    strategy=Strategy.PARALLEL,
)


# ── Sample Input ─────────────────────────────────────────────────

SAMPLE_CODE = """
Review this code:

import os

def process_upload(filename, data):
    path = f"/uploads/{filename}"
    with open(path, "wb") as f:
        f.write(data)
    os.chmod(path, 0o777)
    return path

def get_user(db, user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query).fetchone()

def send_welcome(user):
    print(f"Welcome {user['name']}!")
    return True
"""


# ── Run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        print("Starting parallel code review...\n")
        result = runtime.run(review, SAMPLE_CODE)

        # Print each reviewer's findings
        if result.sub_results:
            for agent_name, sub in result.sub_results.items():
                print(f"\n{'=' * 50}")
                print(f"  {agent_name}")
                print(f"{'=' * 50}")
                print(sub if isinstance(sub, str) else sub.get("result", sub))
        else:
            result.print_result()
