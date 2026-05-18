import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

"""Issue Triage with GitHub + Discord Integration

Same handoff triage as 03_issue_triage_handoff.py, but fetches real
issues from GitHub and routes notifications to Discord channels.

Flow:
    1. You run: runtime.run(triage, "Triage issue #13056 in repo fastapi/fastapi")
    2. Triage agent calls get_issue() to fetch the issue from GitHub
    3. Triage agent reads it, decides: bug, feature, or docs
    4. Hands off to the right specialist (e.g. bug_handler)
    5. Specialist calls search_issues() — checks for duplicates
    6. Specialist calls add_labels() — labels the issue on GitHub
    7. Specialist calls post_comment() — posts analysis on the issue
    8. Specialist calls post_to_discord() — notifies the right channel

Setup:
    pip install agentspan requests
    agentspan server start

    # Store credentials in the AgentSpan UI (localhost:6767 → Credentials):
    #   GITHUB_TOKEN  = GitHub personal access token (needs repo scope)
    #   DISCORD_TOKEN = Discord bot token

    # Discord setup:
    #   1. Go to discord.com/developers/applications → New Application
    #   2. Bot tab → Reset Token → copy it
    #   3. Turn on "Message Content Intent"
    #   4. OAuth2 → URL Generator → select "bot" scope → select permissions:
    #      Send Messages, Read Message History, Add Reactions
    #   5. Open the generated URL to invite the bot to your server
    #   6. Create channels: #bugs, #feature-requests, #docs
    #   7. Copy each channel ID (right-click channel → Copy Channel ID)

    python 03_issue_triage_github_discord.py
"""

import os
import requests
from agentspan.agents import Agent, AgentRuntime, Strategy, tool


# ── Config ───────────────────────────────────────────────────────

GITHUB_API = "https://api.github.com"
DISCORD_API = "https://discord.com/api/v10"

# Replace these with your Discord channel IDs
DISCORD_CHANNELS = {
    "bugs": "1493063643657670726",
    "feature-requests": "REPLACE_WITH_FEATURES_CHANNEL_ID",
    "docs": "REPLACE_WITH_DOCS_CHANNEL_ID",
}


# ── GitHub Tools ─────────────────────────────────────────────────

@tool(credentials=["GITHUB_TOKEN"])
def get_issue(repo: str, issue_number: int) -> dict:
    """Fetch a GitHub issue by number. repo format: owner/repo"""
    token = os.environ["GITHUB_TOKEN"]
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/issues/{issue_number}",
        headers={"Authorization": f"Bearer {token}"},
    )
    issue = resp.json()
    return {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue.get("body", ""),
        "user": issue["user"]["login"],
        "labels": [l["name"] for l in issue.get("labels", [])],
        "state": issue["state"],
        "created_at": issue["created_at"],
    }


@tool(credentials=["GITHUB_TOKEN"])
def search_issues(repo: str, query: str) -> list:
    """Search for similar or duplicate issues in a repo."""
    token = os.environ["GITHUB_TOKEN"]
    resp = requests.get(
        f"{GITHUB_API}/search/issues",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": f"{query} repo:{repo}", "per_page": 5},
    )
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
        }
        for i in resp.json().get("items", [])
    ]


@tool(credentials=["GITHUB_TOKEN"])
def add_labels(repo: str, issue_number: int, labels: list) -> dict:
    """Add labels to a GitHub issue."""
    token = os.environ["GITHUB_TOKEN"]
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/labels",
        headers={"Authorization": f"Bearer {token}"},
        json={"labels": labels},
    )
    return {"status": "labeled", "labels": labels}


@tool(credentials=["GITHUB_TOKEN"])
def post_comment(repo: str, issue_number: int, body: str) -> dict:
    """Post a comment on a GitHub issue."""
    token = os.environ["GITHUB_TOKEN"]
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments",
        headers={"Authorization": f"Bearer {token}"},
        json={"body": body},
    )
    return {"status": "commented", "issue_number": issue_number}


# ── Discord Tools ────────────────────────────────────────────────

@tool(credentials=["DISCORD_TOKEN"])
def post_to_discord(channel_name: str, message: str) -> dict:
    """Post a message to a Discord channel. channel_name: bugs, feature-requests, or docs."""
    token = os.environ["DISCORD_TOKEN"]
    channel_id = DISCORD_CHANNELS.get(channel_name)
    if not channel_id or channel_id.startswith("REPLACE"):
        return {"status": "skipped", "reason": f"Channel ID not configured for #{channel_name}"}
    resp = requests.post(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers={"Authorization": f"Bot {token}"},
        json={"content": message},
    )
    return {"status": "posted", "channel": channel_name}


# ── Specialist Agents ────────────────────────────────────────────

bug_handler = Agent(
    name="bug_handler",
    model="openai/gpt-4o",
    instructions=(
        "You handle bug reports. Read the issue CAREFULLY.\n\n"
        "Do these steps in order:\n"
        "1. Search for duplicate issues using search_issues.\n"
        "2. Add labels: 'bug' + a severity label (P0/P1/P2/P3).\n"
        "3. Post a comment on the GitHub issue with EXACTLY this format:\n"
        "   Severity: P0/P1/P2/P3\n"
        "   Component: <which part>\n"
        "   Repro steps: <what the user described, or 'Not provided'>\n"
        "   Duplicates: <any related issues found, or 'None found'>\n"
        "4. Post a summary to the 'bugs' Discord channel.\n\n"
        "RULES:\n"
        "- ONLY use information the user actually wrote. No guesses.\n"
        "- Do NOT suggest workarounds or fixes.\n"
        "- Do NOT invent details the user didn't provide."
    ),
    tools=[search_issues, add_labels, post_comment, post_to_discord],
)

feature_handler = Agent(
    name="feature_handler",
    model="openai/gpt-4o",
    instructions=(
        "You handle feature requests. Read the issue CAREFULLY.\n\n"
        "Do these steps in order:\n"
        "1. Search for duplicate or related feature requests.\n"
        "2. Add labels: 'enhancement' + an area label.\n"
        "3. Post a comment on the GitHub issue acknowledging the request "
        "and noting any related issues found. Keep it under 100 words.\n"
        "4. Post a summary to the 'feature-requests' Discord channel.\n\n"
        "RULES:\n"
        "- ONLY use information the user actually wrote. No guesses.\n"
        "- Do NOT promise timelines or delivery.\n"
        "- Do NOT invent use cases the user didn't describe."
    ),
    tools=[search_issues, add_labels, post_comment, post_to_discord],
)

docs_handler = Agent(
    name="docs_handler",
    model="openai/gpt-4o",
    instructions=(
        "You handle docs issues and questions. Read the issue CAREFULLY.\n\n"
        "Do these steps in order:\n"
        "1. Add the label 'documentation'.\n"
        "2. Post a reply comment on the GitHub issue — acknowledge the "
        "gap and say the team will update the docs. Under 50 words.\n"
        "3. Post to the 'docs' Discord channel so the docs team sees it.\n\n"
        "RULES:\n"
        "- Do NOT answer the technical question — just acknowledge the gap.\n"
        "- NEVER write code examples. You will get them wrong.\n"
        "- Keep it short. Just acknowledge and commit to updating docs."
    ),
    tools=[add_labels, post_comment, post_to_discord],
)

# ── Fetcher Agent (fetches the issue from GitHub) ────────────────

fetcher = Agent(
    name="fetcher",
    model="openai/gpt-4o",
    instructions=(
        "You fetch GitHub issues. Call get_issue with the repo and "
        "issue_number from the prompt. Return the issue's title and "
        "body verbatim. Do not summarize or analyze."
    ),
    tools=[get_issue],
)

# ── Triage Agent (pure handoff — no tools, just routing) ─────────

triage = Agent(
    name="triage",
    model="openai/gpt-4o",
    agents=[bug_handler, feature_handler, docs_handler],
    strategy=Strategy.HANDOFF,
    instructions=(
        "You are an issue triage bot. Your ONLY job is to route.\n\n"
        "1. Read the issue (you receive it as input).\n"
        "2. Hand off to exactly ONE agent:\n"
        "   - Error/crash/traceback/regression → bug_handler\n"
        "   - Feature request/suggestion → feature_handler\n"
        "   - Docs question/confusion → docs_handler\n"
        "3. After the specialist responds, output their response "
        "VERBATIM. Copy-paste it exactly. Add nothing.\n\n"
        "You are a router, not an analyst. Do NOT add your own words."
    ),
)

# Sequential: fetcher → triage (with handoff sub-agents)
pipeline = fetcher >> triage


# ── Run ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(pipeline, "Triage issue #13056 in repo fastapi/fastapi")
        result.print_result()
