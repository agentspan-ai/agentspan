# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OCG Docs Writer — documentation agent with Open Context Graph.

Uses an OCG sub-agent for codebase discovery, then reads the target file
via the GitHub CLI and proposes an additive documentation change.

Output is a text proposal only — no branches, no commits, no GitHub writes.

Requirements:
    - Conductor server at AGENTSPAN_SERVER_URL
    - OCG service at OCG_BASE_URL (default https://dev.orkescontextgraph.io/api/v1)
    - AGENTSPAN_LLM_MODEL set in environment
"""

import os
import shlex
import subprocess
import base64
import json

from agentspan.agents import Agent, AgentRuntime, agent_tool, tool
from agentspan.agents.integrations.ocg import ocg_agent

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
    """Read-only GitHub CLI. Use for fetching file contents once you have a path."""
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

ocg = agent_tool(
    ocg_agent,
    name="ocg",
    description=(
        "Codebase search. Pass a natural-language request; returns the "
        "relevant file path, entity id, and a summary. Call at most once."
    ),
)

agent = Agent(
    name="ocg_docs_writer",
    model=LLM_MODEL,
    tools=[ocg, gh],
    instructions=(
        "You are a documentation engineer working on the agentspan-ai/agentspan repo.\n\n"
        "TASK: Find the right docs file to edit and propose an additive markdown "
        "section explaining the `AGENTSPAN_LOG_LEVEL` env var "
        "(accepted values: DEBUG, INFO, WARN, ERROR; default: INFO).\n\n"
        "DISCOVERY: call `ocg(request='...')` ONCE to find the target file path. "
        "Then use `gh api repos/agentspan-ai/agentspan/contents/<path>` to read it "
        "(the response auto-caches the file to /tmp — use open() in execute_code).\n\n"
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
