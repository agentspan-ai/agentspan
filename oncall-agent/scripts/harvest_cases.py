"""Turn humans' feedback on live triages into eval cases (step 3 of the improvement loop).

Reads ``triages.jsonl`` and ``feedback.jsonl`` from the listener's store (default
``~/.oncall-agent``) and writes new cases to ``<store>/cases.json``. That file is NOT in
the repo: it describes customer incidents and the repo is public. Each case points at
the incident's recording (``<store>/recordings/<alert execution>.jsonl``), so it replays
offline forever.

* "cause: <truth>" or "wrong"  -> a case the agent currently FAILS; its checks are drafted
                                  from the human's words (``checks_by: llm-draft``)
* "correct"                    -> a regression case locking in the agent's own answer
* questions only               -> a case flagged ``needs_truth`` (answer was not enough)

Checks are drafted by the model so they match on meaning-bearing terms; review them in
``cases.json`` (any case can be edited or set ``"retired": "<why>"``).

    PYTHONPATH=src .venv/bin/python scripts/harvest_cases.py [--store ~/.oncall-agent] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DRAFT_PROMPT = """You write string checks for an on-call triage eval case. A check group is a list
of alternative lowercase terms; the group passes when ANY term appears in the agent's answer.
Use 1-3 groups for the cause, 0-2 for the action. Terms must be short (1-3 words), specific to
THIS root cause, and robust to paraphrase (include synonyms). must_not_mention lists the
specific wrong conclusion the agent reached, if any (0-3 short phrases).

Agent's answer:
{answer}

Human verdict: {verdict}
Human's root cause: {cause}
Human's action: {action}

Reply with ONLY a JSON object: {{"cause_any": [[...]], "action_any": [[...]], "must_not_mention": [...]}}"""


def _rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def _draft_checks(model: str, server: str, answer: str, verdict: str, cause: str, action: str) -> dict:
    from conductor.ai.agents import Agent, AgentRuntime
    from oncall_agent.slack_app import _run_with_deadline
    agent = Agent(name="oncall_case_drafter", model=model, instructions="You output strict JSON only.")
    with AgentRuntime(server_url=server) as rt:
        # Wall-clock bound: an LLM task the server leaves SCHEDULED after network errors hung a run for 13h.
        out = _run_with_deadline(rt, agent, DRAFT_PROMPT.format(answer=answer, verdict=verdict, cause=cause or "-",
                                                action=action or "-"), 300)
    text = out.output.get("result") if isinstance(out.output, dict) else str(out.output)
    if isinstance(text, dict):  # the server already parsed the model's JSON
        return text
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise RuntimeError(f"drafter returned no JSON: {str(text)[:200]}")
    d = json.loads(m.group(0))
    return {k: d.get(k) or [] for k in ("cause_any", "action_any", "must_not_mention")}


def harvest(store: Path, draft, dry_run: bool = False) -> list[dict]:
    triages = {}
    for t in _rows(store / "triages.jsonl"):
        if t.get("alert_execution") and t.get("answer") and not t.get("followup"):
            triages[t["alert_execution"]] = t  # latest answer per alert
    by_alert: dict[str, dict] = {}
    for f in _rows(store / "feedback.jsonl"):
        agg = by_alert.setdefault(f["alert_execution"], {"cluster": f.get("cluster"), "questions": []})
        for k in ("verdict", "cause", "action", "note"):
            if f.get(k):
                agg[k] = f[k]  # latest wins
        if f.get("question"):
            agg["questions"].append(f["question"])
    cases_path = store / "cases.json"
    cases = json.loads(cases_path.read_text()) if cases_path.exists() else []
    known = {c["execution_id"] for c in cases}
    new = []
    for alert, fb in by_alert.items():
        t = triages.get(alert)
        if alert in known or not t:
            continue
        rec = store / "recordings" / f"{alert}.jsonl"
        case = {"id": f"{fb.get('cluster') or 'cluster'}-{alert[:8]}", "execution_id": alert,
                "agent_answer": t["answer"], "human": fb, "ground_truth": "human",
                "recording": rec.exists()}
        if fb.get("verdict") == "correct" and not fb.get("cause"):
            case["cause"] = t["answer"]
        elif fb.get("cause") or fb.get("verdict") == "wrong":
            case["cause"] = fb.get("cause") or f"agent was wrong: {fb.get('note', '')}"
        else:
            case.update(cause="(not given)", needs_truth=True)
        if not case.get("needs_truth"):
            case.update(draft(t["answer"], fb.get("verdict", "wrong"), fb.get("cause", ""), fb.get("action", "")),
                        checks_by="llm-draft")
        # replay needs the alert itself next to the recording
        meta = store / "recordings" / f"{alert}.meta.json"
        if not dry_run and not meta.exists():
            meta.parent.mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps({"start_time": int(t["at"] * 1000), "reason": t.get("alert_text", "")}))
        new.append(case)
    if new and not dry_run:
        cases_path.write_text(json.dumps(cases + new, indent=1) + "\n")
        add_incidents(store, new)
    return new


def add_incidents(store: Path, cases: list[dict]) -> int:
    """Confirmed causes become knowledge-base incidents (looked up in future triages)."""
    path = store / "incidents.jsonl"
    known = {e for r in _rows(path) for e in (r.get("alert_executions") or [])}
    added = 0
    with open(path, "a") as fh:
        for c in cases:
            if c.get("needs_truth") or c["execution_id"] in known:
                continue
            cause = c["cause"]
            if cause.startswith("*Cause*:"):  # 'correct' verdict: the agent's own cause line
                cause = cause.split("\n")[0].removeprefix("*Cause*:").strip()
            terms = sorted({t for g in c.get("cause_any", []) for t in g})
            fh.write(json.dumps({"id": c["id"], "date": None, "clusters": [c["human"].get("cluster")],
                                 "customer": None, "symptoms": terms, "cause": cause,
                                 "fix": c["human"].get("action") or "", "evidence": "",
                                 "alert_executions": [c["execution_id"]], "source": "on-call feedback",
                                 "confirmed": True}) + "\n")
            added += 1
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=os.path.expanduser("~/.oncall-agent"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    from oncall_agent.config import Config
    cfg = Config.from_env()
    new = harvest(Path(args.store),
                  lambda *a: _draft_checks(cfg.model, cfg.agentspan_server_url, *a), args.dry_run)
    for c in new:
        print(f"{'(dry) ' if args.dry_run else ''}new case {c['id']}: "
              f"{'needs truth' if c.get('needs_truth') else c.get('cause_any')}")
    print(f"{len(new)} new case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
