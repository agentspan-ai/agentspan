"""Replay recent real alerts through the triage agent into a scorable report.

The production gate for the on-call agent is a human-scored eval: run the last
couple of days of REAL alerts (deduped to unique incidents) through the agent
in dry-run, write every hypothesis into one markdown report, and have the
on-call engineer mark each Useful / Not useful. No LLM judges anything here —
scoring is the human's (CLAUDE.md rule 1).

Usage (from oncall-agent/, with .env + ANTHROPIC_API_KEY exported):
    PYTHONPATH=src .venv/bin/python scripts/eval_batch.py [--limit 30]
        [--hours 48] [--out /tmp/oncall_eval.md]

The report is generated output — do NOT commit it.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from oncall_agent.config import Config
from oncall_agent.conductor_client import ConductorDispatcher
from oncall_agent.eval_select import select_eval_incidents
from oncall_agent.runtime_compat import summary_text, use_thread_workers_if_needed

log = logging.getLogger("oncall_eval")


def collect_alerting_runs(disp: ConductorDispatcher, hours: int) -> list[dict]:
    """All health_check runs in the window, across every cluster (paginated)."""
    since = int(time.time() * 1000) - hours * 3_600_000
    rows: list[dict] = []
    for page in range(40):
        res = disp._wf.search(
            start=page * 100,
            size=100,
            free_text="health_check",
            query=f"workflowType IN (health_check) AND startTime > {since}",
        )
        batch = getattr(res, "results", None) or []
        if not batch:
            break
        rows += [
            {
                "workflow_id": s.workflow_id,
                "start_time": s.start_time,
                "reason": getattr(s, "reason_for_incompletion", None),
            }
            for s in batch
        ]
    log.info("scanned %d runs in the last %dh", len(rows), hours)
    return rows


def triage_prompt(reason: str, execution_id: str) -> str:
    return (
        "A cluster health-check alert fired.\n\n"
        f"Alert text:\n{reason}\n\n"
        f"The failing health_check execution id is: {execution_id}\n"
        "Investigate (read-only) and produce the triage summary."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="On-call triage eval batch")
    parser.add_argument("--limit", type=int, default=30, help="max unique incidents")
    parser.add_argument("--hours", type=int, default=48, help="lookback window")
    parser.add_argument("--out", default="/tmp/oncall_eval.md", help="report path")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    use_thread_workers_if_needed()
    cfg = Config.from_env()
    disp = ConductorDispatcher(
        cfg.conductor_server_url, cfg.conductor_key_id, cfg.conductor_key_secret
    )

    incidents = select_eval_incidents(collect_alerting_runs(disp, args.hours), args.limit)
    log.info("selected %d unique incidents", len(incidents))
    if not incidents:
        print("no incidents in window", file=sys.stderr)
        return 1

    from conductor.ai.agents import AgentRuntime

    from oncall_agent.agent import build_agent

    lines = [
        "# On-call triage eval batch",
        "",
        f"{len(incidents)} unique incidents from the last {args.hours}h "
        f"(flappers deduped). For each: mark **Score** Useful / Partly / Wrong "
        f"and add a note when the hypothesis missed.",
        "",
    ]
    ok = 0
    with AgentRuntime(server_url=cfg.agentspan_server_url) as runtime:
        agent = build_agent(cfg.model)
        for i, inc in enumerate(incidents, 1):
            wf_id, reason = inc["workflow_id"], str(inc["reason"])
            log.info("[%d/%d] triaging %s", i, len(incidents), wf_id)
            started = time.time()
            try:
                result = runtime.run(agent, triage_prompt(reason, wf_id))
                summary = summary_text(result)
            except Exception as exc:  # keep the batch going; the report shows it
                summary = f"TRIAGE FAILED: {exc}"
                log.exception("[%d/%d] failed", i, len(incidents))
            else:
                ok += 1
            lines += [
                f"## {i}. `{wf_id}`",
                "",
                f"*Fired*: {inc.get('start_time')} — "
                f"[execution](https://ah5r-prod.orkesconductor.com/execution/{wf_id}) — "
                f"took {time.time() - started:.0f}s",
                "",
                "**Alert**:",
                "",
                "```",
                reason.strip(),
                "```",
                "",
                "**Agent triage**:",
                "",
                summary,
                "",
                "**Score**: [ ] Useful  [ ] Partly  [ ] Wrong",
                "",
                "**Note**:",
                "",
                "---",
                "",
            ]
            # Flush after every incident so a crash loses nothing.
            with open(args.out, "w") as fh:
                fh.write("\n".join(lines))

    log.info("done: %d/%d triaged OK -> %s", ok, len(incidents), args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
