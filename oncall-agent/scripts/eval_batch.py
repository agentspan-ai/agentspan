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
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from oncall_agent.config import Config
from oncall_agent.conductor_client import ConductorDispatcher
from oncall_agent.eval_select import select_eval_incidents
from oncall_agent.grading import describe, grade, passed as graded_pass
from oncall_agent.runtime_compat import summary_text, use_thread_workers_if_needed
from oncall_agent.slack_app import _run_with_deadline

CASE_DEADLINE_S = 900

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
    from oncall_agent.kb import leads_for_alert
    return (
        "A cluster health-check alert fired.\n\n"
        f"Alert text:\n{reason}\n\n"
        f"The failing health_check execution id is: {execution_id}\n"
        # same prompt as the listener, with this case's own incident hidden (leave-one-out)
        + (leads_for_alert(reason, exclude_execution=execution_id) if os.environ.get("ONCALL_EVAL_KB", "1") == "1" else "")
        + "Investigate (read-only) and produce the triage summary."
    )


def load_cases(path: str, disp: ConductorDispatcher | None, replay: str | None = None,
               record: str | None = None, only: list[str] | None = None) -> list[dict]:
    """Ground-truth cases: each alert's execution plus the checks its triage must pass.

    Replaying reads the alert from the recording, so no Conductor call is made."""
    cases = [c for c in json.load(open(path)) if not c.get("retired") and not c.get("needs_truth")
             and (not only or c["id"] in only)]
    for case in list(cases):
        meta = Path(replay or record or ".") / f"{case['execution_id']}.meta.json"
        if replay:
            if not meta.exists():
                log.warning("skipping %s: no recording in %s (record it live first)", case["id"], replay)
                cases.remove(case)
                continue
            alert = json.loads(meta.read_text())
        else:
            wf = disp._wf.get_workflow(case["execution_id"], include_tasks=False)
            alert = {"start_time": wf.start_time, "reason": wf.reason_for_incompletion}
            if record:
                meta.parent.mkdir(parents=True, exist_ok=True)
                meta.write_text(json.dumps(alert))
        case.update(workflow_id=case["execution_id"], **alert)
    return cases


def replay_misses(replay_dir: str, execution_id: str) -> list[str]:
    """Tools the agent called during replay that the recording never captured."""
    path = Path(replay_dir) / "_misses.jsonl"
    if not path.exists():
        return []
    return [m["tool"] for m in map(json.loads, path.read_text().splitlines()) if m["execution_id"] == execution_id]


# Read once per recorded case even if the agent did not, so a later playbook that asks for them
# can be judged in replay (a recording without the evidence can never pass, whatever the prompt).
EVIDENCE_PACK = ("get_incident_details", "get_alert_recurrence", "get_node_churn", "get_pods_data",
                 "get_restart_reasons", "get_db_connections", "get_cluster_metrics")


def record_evidence_pack(execution_id: str, record_dir: str) -> list[str]:
    from oncall_agent.tools import ALL_TOOLS
    done = set()
    path = Path(record_dir) / f"{execution_id}.jsonl"
    if path.exists():
        done = {json.loads(l)["tool"] for l in path.read_text().splitlines() if l.strip()}
    added = []
    for t in ALL_TOOLS:
        name = t._tool_def.name
        if name in EVIDENCE_PACK and name not in done:
            try:
                t._tool_def.func(execution_id=execution_id)  # cassette-wrapped: recorded like any call
                added.append(name)
            except Exception as exc:
                log.warning("evidence %s failed for %s: %s", name, execution_id, exc)
    return added


def record_history(path: str, mode: str, model: str, results: dict[str, dict]) -> list[str]:
    """Append this run to the history file; return how it differs from the last run in the same mode."""
    prev = None
    if os.path.exists(path):
        runs = [json.loads(l) for l in open(path) if l.strip()]
        prev = next((r for r in reversed(runs) if r["mode"] == mode), None)
    recorded_at = None
    if mode == "replay":
        recorded_at = os.environ.get("ONCALL_REPLAY_DIR")
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    run = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "git": sha, "mode": mode, "recordings": recorded_at, "model": model,
           "passed": sum(r["passed"] for r in results.values()), "total": len(results), "cases": results}
    with open(path, "a") as fh:
        fh.write(json.dumps(run) + "\n")
    if not prev:
        return []
    before = {cid: r["passed"] for cid, r in prev["cases"].items()}
    return ([f"REGRESSED {cid}: {r['result']}" for cid, r in results.items() if before.get(cid) and not r["passed"]]
            + [f"fixed {cid}" for cid, r in results.items() if before.get(cid) is False and r["passed"]])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="On-call triage eval batch")
    parser.add_argument("--limit", type=int, default=30, help="max unique incidents")
    parser.add_argument("--hours", type=int, default=48, help="lookback window")
    parser.add_argument("--out", default="/tmp/oncall_eval.md", help="report path")
    parser.add_argument("--cases", help="ground-truth cases JSON (eval/cases.json) instead of recent alerts")
    parser.add_argument("--history", default="eval/history.jsonl", help="per-run scores, appended")
    parser.add_argument("--only", action="append", metavar="CASE_ID", help="run just these case ids")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--record", metavar="DIR", help="save every tool call (and the alert) per case to DIR")
    mode.add_argument("--replay", metavar="DIR", help="answer tool calls from a recording in DIR; no live reads")
    args = parser.parse_args(argv)
    if args.replay and not args.cases:
        parser.error("--replay needs --cases")
    # Set before the tool workers start; they read it on every call (see cassette.py).
    if args.record:
        os.environ["ONCALL_RECORD_DIR"] = os.path.abspath(args.record)
    if args.replay:
        os.environ["ONCALL_REPLAY_DIR"] = os.path.abspath(args.replay)
        (Path(args.replay) / "_misses.jsonl").unlink(missing_ok=True)  # misses of THIS run only

    logging.basicConfig(level=logging.INFO)
    use_thread_workers_if_needed()
    cfg = Config.from_env()
    disp = None if args.replay else ConductorDispatcher(
        cfg.conductor_server_url, cfg.conductor_key_id, cfg.conductor_key_secret
    )

    if args.cases:
        incidents = load_cases(args.cases, disp, args.replay, args.record, args.only)
    else:
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
    passed = 0
    graded: dict[str, dict] = {}
    with AgentRuntime(server_url=cfg.agentspan_server_url) as runtime:
        agent = build_agent(cfg.model, actions="propose", isolated=True)  # eval never executes a change
        for i, inc in enumerate(incidents, 1):
            wf_id, reason = inc["workflow_id"], str(inc["reason"])
            log.info("[%d/%d] triaging %s", i, len(incidents), wf_id)
            started = time.time()
            try:
                # Wall-clock bound per case: a run whose tool workers stop polling (seen after the
                # laptop slept) would otherwise hang the whole batch for hours.
                result = _run_with_deadline(runtime, agent, triage_prompt(reason, wf_id), CASE_DEADLINE_S)
                status = str(getattr(result, "status", "COMPLETED") or "COMPLETED").upper()
                if status != "COMPLETED":
                    raise RuntimeError(f"agent run ended {status}")
                summary = summary_text(result)  # raises TriageIncomplete without a Cause line
            except Exception as exc:  # keep the batch going; the report shows it
                summary = f"TRIAGE FAILED: {exc}"
                log.exception("[%d/%d] failed", i, len(incidents))
            else:
                ok += 1
            if args.record:
                log.info("evidence pack recorded: %s", record_evidence_pack(wf_id, args.record))
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
            ]
            if "cause" in inc:
                result = grade(inc, summary) if not summary.startswith("TRIAGE FAILED") else {"run": [summary]}
                ok_case = graded_pass(result)
                passed += ok_case
                graded[inc["id"]] = {"passed": ok_case, "result": describe(result),
                                     "seconds": round(time.time() - started), "answer": summary[:1500]}
                if args.replay:
                    graded[inc["id"]]["notRecorded"] = replay_misses(args.replay, wf_id)
                lines += [
                    f"**Known cause** ({inc.get('ground_truth')}): {inc['cause']}",
                    "",
                    f"**Check**: {describe(result)}"
                    + (f" — replay missing: {graded[inc['id']]['notRecorded']}" if graded[inc["id"]].get("notRecorded") else ""),
                    "",
                ]
            lines += [
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

    log.info("done: %d/%d triaged OK, %d passed checks -> %s", ok, len(incidents), passed, args.out)
    print(args.out)
    if not graded:
        return 0
    mode = "replay" if args.replay else "live"
    changes = record_history(args.history, mode, cfg.model, graded)
    print(f"{passed}/{len(graded)} cases pass ({mode})")
    for change in changes:
        print(change)
    return 0 if passed == len(graded) else 1


if __name__ == "__main__":
    raise SystemExit(main())
