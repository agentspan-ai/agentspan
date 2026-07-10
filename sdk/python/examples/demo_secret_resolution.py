# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Local e2e proof — embedded host (Orkes Conductor) resolves secrets.

Minimal: ONE worker tool + an LLM call, so a single run exercises BOTH embedded
secret paths and the Orkes UI shows the result:

  * Worker-tool secret  -> the tool declares credentials=["DEMO_SECRET"] and reads it
    with get_secret(). Embedded, the compiler stamps
    inputParameters.__resolved_credentials__ = {DEMO_SECRET: "${workflow.secrets.DEMO_SECRET}"}
    and the host resolves it at poll. The tool returns a masked confirmation.
  * LLM apiKey secret   -> the agent makes an LLM call; embedded, the apiKey is stamped
    ${workflow.secrets.<PROVIDER_KEY>} and resolved by the host. If the LLM step succeeds,
    that secret resolved too.

The tool does NO external network calls, so the task output is a clean, deterministic
"secret_resolved: true" you can screenshot.

--------------------------------------------------------------------------------
Setup (agentspan embedded in local Orkes, agentspan.embedded=true):

1) In Orkes create the secrets (UI: Definitions -> Secrets, or the secrets API):
     DEMO_SECRET    = demo-value-12345
     OPENAI_API_KEY = <your key>     # or the key matching AGENTSPAN_LLM_MODEL's provider
                                     # (anthropic -> ANTHROPIC_API_KEY, etc.)

2) Point the SDK at your local Orkes and give it an app key/secret:
     export AGENTSPAN_SERVER_URL=http://localhost:8080/api
     export AGENTSPAN_AUTH_KEY=<orkes-app-key>
     export AGENTSPAN_AUTH_SECRET=<orkes-app-secret>
     export AGENTSPAN_LLM_MODEL=openai/gpt-4o

3) Run:
     cd sdk/python/examples
     uv run python demo_secret_resolution.py

Screenshot: in the Orkes UI open this execution -> the check_secret task's output
shows {"secret_resolved": true, "value_length": 16, "value_prefix": "demo…"}.

CI smoke check: the script exits 0 only if the secret resolved AND the workflow
completed; otherwise it prints "SMOKE FAIL ..." and exits 1 (so it can gate CI).
"""

from settings import settings

from conductor.ai.agents import (
    Agent,
    AgentRuntime,
    CredentialNotFoundError,
    get_secret,
    tool,
)


@tool(credentials=["DEMO_SECRET"])
def check_secret() -> dict:
    """Report whether the declared secret was resolved by the host. No external calls.

    Returns a MASKED confirmation only — never logs or returns the full secret.
    """
    try:
        value = get_secret("DEMO_SECRET")
    except CredentialNotFoundError:
        return {"secret_resolved": False, "detail": "DEMO_SECRET was not delivered to the worker"}
    return {
        "secret_resolved": True,
        "value_length": len(value),
        "value_prefix": (value[:4] + "…") if value else "",
    }


agent = Agent(
    name="secret_resolution_demo",
    model=settings.llm_model,
    tools=[check_secret],
    credentials=["DEMO_SECRET"],
    instructions=(
        "Call the check_secret tool exactly once, then state whether the secret "
        "resolved and its length. Never invent or guess a secret value."
    ),
)


def _secret_resolved(result) -> bool:
    """True iff the check_secret tool ran and reported secret_resolved=True."""
    for call in result.tool_calls:
        if call.get("name") != "check_secret" or "result" not in call:
            continue
        out = call["result"]
        # Tool returns its dict directly; tolerate a {"result": {...}} wrapper too.
        if isinstance(out, dict) and isinstance(out.get("result"), dict):
            out = out["result"]
        if isinstance(out, dict) and out.get("secret_resolved") is True:
            return True
    return False


if __name__ == "__main__":
    import sys

    with AgentRuntime() as runtime:
        result = runtime.run(agent, "Did my secret resolve? Use the tool to check.")
        result.print_result()

    ok = result.is_success and _secret_resolved(result)
    print("-" * 60)
    if ok:
        print("✅ SMOKE PASS — host resolved DEMO_SECRET (and the LLM call succeeded).")
        sys.exit(0)
    reason = (
        "workflow did not complete successfully"
        if not result.is_success
        else "check_secret did not report secret_resolved=true "
        "(secret not delivered, tool not called, or running standalone)"
    )
    print(f"❌ SMOKE FAIL — {reason}. status={result.status}")
    sys.exit(1)
