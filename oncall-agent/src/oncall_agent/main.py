"""Entry point.

Two modes:
  * ``python -m oncall_agent.main``                 -> start the Slack listener
  * ``python -m oncall_agent.main triage <exec_id>`` -> triage one execution and print
    the summary (handy for local testing / historical replay, no Slack needed)
"""
from __future__ import annotations

import sys

from .config import Config


def triage_once(execution_id: str) -> str:
    from agentspan.agents import AgentRuntime

    from .agent import build_agent

    cfg = Config.from_env()
    agent = build_agent(cfg.model)
    prompt = (
        f"A cluster health-check alert fired for execution id {execution_id}. "
        "Investigate (read-only) and produce the triage summary."
    )
    with AgentRuntime(server_url=cfg.agentspan_server_url) as runtime:
        result = runtime.run(agent, prompt)
    return getattr(result, "output", None) or str(result)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "triage":
        if len(argv) < 2:
            print("usage: python -m oncall_agent.main triage <execution_id>")
            return 2
        print(triage_once(argv[1]))
        return 0

    from .slack_app import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
