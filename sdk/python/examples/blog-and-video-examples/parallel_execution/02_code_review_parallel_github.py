import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

"""Parallel Code Review with GitHub Integration

Same parallel review as 02_code_review_parallel.py, but fetches a real
PR diff from GitHub and posts the review as a PR comment.

Setup:
    pip install agentspan requests
    agentspan server start

    # Store credentials in the AgentSpan UI (localhost:6767 → Credentials):
    #   GITHUB_TOKEN = your GitHub personal access token (needs repo scope)

    python 02_code_review_parallel_github.py
"""

import os
import requests
from agentspan.agents import Agent, AgentRuntime, Strategy, tool


# ── GitHub Tools ─────────────────────────────────────────────────

GITHUB_API = "https://api.github.com"


@tool(credentials=["GITHUB_TOKEN"])
def get_pr_diff(repo: str, pr_number: int) -> dict:
    """Fetch the diff for a GitHub pull request. repo format: owner/repo"""
    token = os.environ["GITHUB_TOKEN"]
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3.diff",
        },
    )
    pr_info = requests.get(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    return {
        "title": pr_info.get("title", ""),
        "description": pr_info.get("body", ""),
        "diff": resp.text[:10000],  # truncate large diffs
        "files_changed": pr_info.get("changed_files", 0),
        "additions": pr_info.get("additions", 0),
        "deletions": pr_info.get("deletions", 0),
    }


@tool(credentials=["GITHUB_TOKEN"])
def post_pr_review(repo: str, pr_number: int, body: str) -> dict:
    """Post a review comment on a GitHub pull request."""
    token = os.environ["GITHUB_TOKEN"]
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        },
        json={"body": body, "event": "COMMENT"},
    )
    return {"status": "posted", "pr_number": pr_number}


# ── Agents ────────────────────────────────────────────────────────

bug_reviewer = Agent(
    name="bug_reviewer",
    model="openai/gpt-4o",
    instructions=(
        "You are a senior software engineer reviewing a code diff. "
        "Read the ACTUAL code in the diff carefully. Only report issues "
        "you can point to in specific lines. For each issue, quote the "
        "exact code and explain what's wrong.\n\n"
        "Look for: logic errors, unhandled edge cases, crashes, and "
        "incorrect behavior.\n\n"
        "IMPORTANT: If the code has no bugs, say 'No bugs found.' "
        "Do NOT invent issues. Do NOT give generic advice. Only report "
        "problems you can see in the actual code."
    ),
)

security_reviewer = Agent(
    name="security_reviewer",
    model="openai/gpt-4o",
    instructions=(
        "You are an application security engineer reviewing a code diff. "
        "Read the ACTUAL code in the diff carefully. Only report "
        "vulnerabilities you can point to in specific lines.\n\n"
        "Look for: injection flaws, insecure defaults, data exposure, "
        "missing input validation, OWASP Top 10 issues. Rate each "
        "finding as Critical, High, Medium, or Low.\n\n"
        "IMPORTANT: If the code has no security issues, say 'No security "
        "issues found.' Do NOT invent vulnerabilities. Do NOT give "
        "generic security advice."
    ),
)

style_reviewer = Agent(
    name="style_reviewer",
    model="openai/gpt-4o",
    instructions=(
        "You are a Python code quality reviewer reviewing a code diff. "
        "Read the ACTUAL code in the diff carefully. Only report style "
        "issues you can point to in specific lines.\n\n"
        "Look for: missing type hints, missing docstrings, hardcoded "
        "values, print vs logging, naming issues, readability.\n\n"
        "IMPORTANT: If the code style is good, say 'Code style looks "
        "good.' Do NOT invent issues. Do NOT give generic advice."
    ),
)

# ── Pipeline: fetch → parallel review → summarize + post ─────────

fetcher = Agent(
    name="pr_fetcher",
    model="openai/gpt-4o",
    instructions=(
        "You are a helper that fetches PR diffs. Call the get_pr_diff "
        "tool and return the COMPLETE diff verbatim as your output. "
        "Do not summarize or shorten it. Output the raw diff exactly "
        "as returned by the tool."
    ),
    tools=[get_pr_diff],
)

review = Agent(
    name="code_review",
    model="openai/gpt-4o",
    agents=[bug_reviewer, security_reviewer, style_reviewer],
    strategy=Strategy.PARALLEL,
)

summarizer = Agent(
    name="summarizer",
    model="openai/gpt-4o",
    instructions=(
        "You are a tech lead. Given three code review outputs (bugs, "
        "security, style), combine them into a single review in markdown "
        "with sections: ## Bugs, ## Security, ## Style, "
        "## Verdict (APPROVE / REQUEST CHANGES / NEEDS DISCUSSION). "
        "Output ONLY the markdown review, nothing else."
    ),
)

# Sequential: fetch diff → parallel review → summarize
pipeline = fetcher >> review >> summarizer


# ── Run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    REPO = "deeptireddy-lab/agentspan-metrics"
    PR_NUMBER = 1

    with AgentRuntime() as runtime:
        print(f"Starting parallel code review for {REPO}#{PR_NUMBER}...\n")
        result = runtime.run(
            pipeline,
            f"Fetch and review GitHub PR {REPO}#{PR_NUMBER}. Use repo='{REPO}' and pr_number={PR_NUMBER} for all GitHub tool calls.",
        )

        # Post the review to GitHub
        review_body = result.output["result"]
        print("Posting review to GitHub...\n")
        token = os.environ.get("GITHUB_TOKEN", "")

        if token:
            resp = requests.post(
                f"{GITHUB_API}/repos/{REPO}/pulls/{PR_NUMBER}/reviews",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={"body": review_body, "event": "COMMENT"},
            )
            if resp.status_code == 200:
                print("Review posted successfully!")
            else:
                print(f"Failed to post: {resp.status_code} {resp.text[:200]}")
        else:
            print("No GITHUB_TOKEN found — review not posted.")
            print("\nReview output:\n")
            print(review_body)
