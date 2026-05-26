# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""GH Docs Writer — documentation agent using GitHub CLI only.

Finds and reads files using the GitHub CLI, then proposes an additive
documentation change.

Output is a text proposal only — no branches, no commits, no GitHub writes.

Requirements:
    - Conductor server at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set in environment
    - gh CLI authenticated
"""

import os
import shlex
import subprocess
import base64
import json

from agentspan.agents import Agent, AgentRuntime, tool

LLM_MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-20250514")


# --- Read-only gh tool with auto-cache -------------------------------------

def _maybe_cache_file_content(stdout: str) -> str:
    if not stdout or not stdout.strip().startswith("{"):
        return stdout
    try:
        d = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return stdout
    if not isinstance(d, dict):
        return stdout
    if d.get("encoding") != "base64" or "content" not in d or "path" not in d:
        return stdout
    try:
        decoded = base64.b64decode(d.get("content", ""))
    except Exception:
        return stdout
    cache_path = os.path.join("/tmp", os.path.basename(d.get("path", "file")))
    try:
        open(cache_path, "wb").write(decoded)
    except OSError:
        return stdout
    cleaned = {k: v for k, v in d.items() if k != "content"}
    cleaned["_cache_path"] = cache_path
    cleaned["_cached_bytes"] = len(decoded)
    cleaned["_note"] = f"file cached at {cache_path} — read via open('{cache_path}').read() in execute_code"
    return json.dumps(cleaned)


@tool(timeout_seconds=30)
def gh(args: str) -> dict:
    """GitHub CLI. Use to search code, list directories, and read files.

    Examples:
        gh('api repos/agentspan-ai/agentspan/contents/docs')
        gh('api repos/agentspan-ai/agentspan/contents/README.md')
        gh('api "search/code?q=AGENTSPAN_LOG_LEVEL+repo:agentspan-ai/agentspan"')
    """
    if not args or not isinstance(args, str):
        return {"error": "missing_args", "exit_code": -1}
    tokens = shlex.split(args)
    blocked = {"create","delete","close","merge","edit","rename","fork",
               "archive","transfer","comment","reopen","lock"} & set(tokens)
    if blocked:
        return {"error": f"blocked: {sorted(blocked)}", "exit_code": -1}
    try:
        r = subprocess.run(["gh", *tokens], capture_output=True, text=True, timeout=25)
    except FileNotFoundError:
        return {"error": "gh not found", "exit_code": -1}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "exit_code": -1}
    return {"stdout": _maybe_cache_file_content(r.stdout), "stderr": r.stderr, "exit_code": r.returncode}


# --- Agent -----------------------------------------------------------------

agent = Agent(
    name="gh_docs_writer",
    model=LLM_MODEL,
    tools=[gh],
    instructions=(
        "You are a documentation engineer working on the agentspan-ai/agentspan repo.\n\n"
        "TASK: Find the right docs file to edit and propose an additive markdown "
        "section explaining the `AGENTSPAN_LOG_LEVEL` env var "
        "(accepted values: DEBUG, INFO, WARN, ERROR; default: INFO).\n\n"
        "Use `gh` to search and navigate the repo:\n"
        "  - search: `gh api 'search/code?q=AGENTSPAN_LOG_LEVEL+repo:agentspan-ai/agentspan'`\n"
        "  - list a dir: `gh api repos/agentspan-ai/agentspan/contents/<path>`\n"
        "  - read a file: `gh api repos/agentspan-ai/agentspan/contents/<path>`\n"
        "    (file content auto-caches to /tmp — read via open() in execute_code)\n\n"
        "OUTPUT — when ready, write ONLY this and nothing else:\n\n"
        "    FILE: <path/to/file.md>\n"
        "    ---\n"
        "    <the markdown snippet to add>\n\n"
        "The snippet MUST include: AGENTSPAN_LOG_LEVEL, DEBUG, INFO, WARN, ERROR, "
        "and state that the default is INFO. Do NOT create branches or commits."
    ),
    local_code_execution=True,
    thinking_budget_tokens=1024,
    max_tokens=8192,
    max_turns=20,
    timeout_seconds=600,
)

PROMPT = "The `AGENTSPAN_LOG_LEVEL` env var is barely documented in the agentspan-ai/agentspan repo. Find the right docs file and propose an additive markdown section explaining it — what values it accepts and what the default is. Output in FILE:/--- format. No commits."

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, PROMPT)
        result.print_result()
