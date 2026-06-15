"""Entry point.

Modes:
  * ``python -m oncall_agent.main``                  -> poll the Slack alert channel once
  * ``python -m oncall_agent.main --loop``           -> poll continuously (every interval)
  * ``python -m oncall_agent.main triage <exec_id>`` -> triage one execution and print the
    summary (handy for local testing / historical replay, no Slack needed)
"""
from __future__ import annotations

import argparse
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

    # Direct triage of a single execution id — no Slack needed.
    if argv and argv[0] == "triage":
        if len(argv) < 2:
            print("usage: python -m oncall_agent.main triage <execution_id>")
            return 2
        print(triage_once(argv[1]))
        return 0

    parser = argparse.ArgumentParser(prog="oncall_agent", description="On-call triage agent")
    parser.add_argument("--loop", action="store_true", help="poll continuously")
    parser.add_argument("--interval", type=int, default=None, help="poll interval seconds (loop mode)")
    args = parser.parse_args(argv)

    from .slack_app import run

    run(loop=args.loop, interval=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
