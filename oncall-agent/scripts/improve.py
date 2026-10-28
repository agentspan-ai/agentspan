"""Steps 4-6 of the improvement loop: propose a playbook fix, gate it on the eval, open a PR.

1. Baseline: replay every eval case (public ``eval/cases.json`` + private
   ``~/.oncall-agent/cases.json``) on the current code.
2. For the failing cases, an improver model reads the case (the known cause and what was
   checked), the agent's answer and the tools it called, plus the current playbook, and
   proposes small edits to the playbook text (``agent.INSTRUCTIONS``) — nothing else.
3. The edits are applied in a throwaway git worktree on a new branch and every case is
   replayed again. The change is KEPT only if it fixes at least one failing case and breaks
   none that passed. Otherwise the improver gets the result and one more attempt.
4. Kept: committed on the branch and a PR is opened (counts only in its body — the repo is
   public). A human reviews and merges; nothing reaches the live listener before that.

Guard rails: only the playbook string changes; the safety rules (read-only investigation,
approval before any change, at most one change) must survive every edit verbatim.

    PYTHONPATH=src .venv/bin/python scripts/improve.py [--attempts 2] [--no-pr]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # oncall-agent/
REPO = HERE.parent                                      # git root
STORE = Path(os.environ.get("ONCALL_STORE", os.path.expanduser("~/.oncall-agent")))
SUITES = [  # (cases file, recordings dir)
    (HERE / "eval" / "cases.json", HERE / "eval" / "recordings"),
    (STORE / "cases.json", STORE / "recordings"),
]
PROTECTED = [  # must survive every edit, verbatim
    "Your investigation tools are STRICTLY READ-ONLY.",
    "every one of them is approved by a human",
    "propose AT\nMOST ONE change",
    "If it is rejected, stop.",
]

IMPROVER_PROMPT = """You improve the playbook (system prompt) of an on-call triage agent for Orkes
Conductor clusters. Below are eval cases it FAILS: the known root cause, what the grader checks,
the agent's answer, and the tools it called (truncated outputs). Find what in the playbook led it
astray or what guidance is missing, and propose the SMALLEST edits that would make it reach the
known cause from the same evidence — general rules that hold for any cluster, never a rule
naming one customer or case. Do not touch the CHANGES/approval rules or the OUTPUT format.

Each edit replaces one exact, unique substring of the playbook ("old") with "new". To add a rule,
use an existing line as "old" and repeat it in "new" with the rule appended.

{previous}PLAYBOOK:
<<<
{playbook}
>>>

FAILING CASES:
{cases}

Reply with ONLY JSON: {{"edits": [{{"old": "...", "new": "...", "why": "..."}}], "reasoning": "..."}}"""


def sh(args: list[str], cwd: Path, env: dict | None = None, check=True) -> str:
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
    if check and p.returncode not in (0, 1):  # eval exits 1 when any case fails
        raise RuntimeError(f"{' '.join(args[:3])} failed: {p.stderr[-800:]}")
    return p.stdout


def run_suite(root: Path, cases: Path, recordings: Path, tag: str) -> dict:
    """Replay one suite on the code under ``root``; returns {case id: graded result}."""
    if not cases.exists() or not recordings.exists():
        return {}
    hist = Path(tempfile.mkdtemp()) / f"{tag}.jsonl"
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    sh([sys.executable, "-u", "scripts/eval_batch.py", "--cases", str(cases), "--replay", str(recordings),
        "--history", str(hist), "--out", str(hist.with_suffix(".md"))], cwd=root, env=env)
    runs = [json.loads(l) for l in hist.read_text().splitlines() if l.strip()] if hist.exists() else []
    return runs[-1]["cases"] if runs else {}


def run_all(root: Path, tag: str) -> dict:
    out = {}
    for i, (cases, rec) in enumerate(SUITES):
        out.update(run_suite(root, cases, rec, f"{tag}-{i}"))
    return out


def trace(recordings: Path, execution_id: str, per_call: int = 700) -> str:
    path = recordings / f"{execution_id}.jsonl"
    if not path.exists():
        return "(no recording)"
    lines = []
    for c in map(json.loads, path.read_text().splitlines()):
        body = json.dumps(c.get("result", c.get("error")), default=str)
        args = {k: v for k, v in c["args"].items() if k != "execution_id"}
        lines.append(f"- {c['tool']}({args}) -> {body[:per_call]}")
    return "\n".join(lines)[:6000]


def failing_context(results: dict) -> str:
    blocks = []
    for cases_file, rec in SUITES:
        if not cases_file.exists():
            continue
        for c in json.loads(cases_file.read_text()):
            r = results.get(c["id"])
            if not r or r["passed"]:
                continue
            checks = {k: c[k] for k in ("cause_any", "must_mention_any", "action_any", "must_not_mention") if c.get(k)}
            blocks.append(f"### {c['id']}\nKNOWN CAUSE: {c.get('cause')}\nCHECKS: {json.dumps(checks)}\n"
                          f"GRADE: {r['result']}\nAGENT ANSWER:\n{r.get('answer', '')}\n"
                          f"TOOLS CALLED:\n{trace(rec, c['execution_id'])}\n")
    return "\n".join(blocks)


def ask_improver(model: str, server: str, playbook: str, cases: str, previous: str) -> dict:
    from conductor.ai.agents import Agent, AgentRuntime
    agent = Agent(name="oncall_playbook_improver", model=model, instructions="You output strict JSON only.")
    with AgentRuntime(server_url=server) as rt:
        out = rt.run(agent, IMPROVER_PROMPT.format(playbook=playbook, cases=cases, previous=previous))
    text = out.output.get("result") if isinstance(out.output, dict) else str(out.output)
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise RuntimeError(f"improver returned no JSON: {str(text)[:300]}")
    return json.loads(m.group(0))


def apply_edits(playbook: str, edits: list[dict]) -> str:
    for e in edits:
        if playbook.count(e["old"]) != 1:
            raise ValueError(f"edit target is not a unique substring: {e['old'][:80]!r}")
        playbook = playbook.replace(e["old"], e["new"])
    missing = [p for p in PROTECTED if p not in playbook]
    if missing:
        raise ValueError(f"edit removed protected safety rules: {missing}")
    return playbook


def verdict(before: dict, after: dict) -> tuple[bool, list[str], list[str]]:
    fixed = [k for k, r in after.items() if r["passed"] and not before.get(k, {}).get("passed", True)]
    broke = [k for k, r in after.items() if not r["passed"] and before.get(k, {}).get("passed")]
    return bool(fixed) and not broke, fixed, broke


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--no-pr", action="store_true")
    ap.add_argument("--model", default=os.environ.get("ONCALL_IMPROVER_MODEL"))
    args = ap.parse_args()
    sys.path.insert(0, str(HERE / "src"))
    from oncall_agent.agent import INSTRUCTIONS
    from oncall_agent.config import Config
    cfg = Config.from_env()
    model = args.model or cfg.model

    print("baseline replay...", flush=True)
    before = run_all(HERE, "before")
    failing = [k for k, r in before.items() if not r["passed"]]
    print(f"baseline: {len(before) - len(failing)}/{len(before)} pass; failing: {failing}", flush=True)
    if not failing:
        return 0

    stamp = time.strftime("%Y%m%d-%H%M")
    branch, wt = f"oncall-improve/{stamp}", Path(tempfile.mkdtemp()) / "wt"
    sh(["git", "worktree", "add", "-q", "-b", branch, str(wt), "HEAD"], cwd=REPO)
    wt_agent = wt / "oncall-agent"
    previous = ""
    try:
        for attempt in range(1, args.attempts + 1):
            proposal = ask_improver(model, cfg.agentspan_server_url, INSTRUCTIONS, failing_context(before), previous)
            try:
                new_playbook = apply_edits(INSTRUCTIONS, proposal.get("edits") or [])
            except ValueError as exc:
                previous = f"YOUR PREVIOUS EDITS WERE INVALID: {exc}\n\n"
                print(f"attempt {attempt}: invalid edits — {exc}", flush=True)
                continue
            src = (HERE / "src" / "oncall_agent" / "agent.py").read_text()
            (wt_agent / "src" / "oncall_agent" / "agent.py").write_text(src.replace(INSTRUCTIONS, new_playbook))
            print(f"attempt {attempt}: {len(proposal['edits'])} edit(s); replaying...", flush=True)
            after = run_all(wt_agent, f"after{attempt}")
            ok, fixed, broke = verdict(before, after)
            print(f"attempt {attempt}: fixed={fixed} broke={broke}", flush=True)
            if ok:
                passed = sum(r["passed"] for r in after.values())
                msg = (f"oncall-agent: playbook fix from the improvement loop ({stamp})\n\n"
                       f"Replay eval: {len(before) - len(failing)}/{len(before)} -> {passed}/{len(after)} pass; "
                       f"fixed {len(fixed)}, broke 0.\n\n" + "\n".join(f"- {e['why']}" for e in proposal["edits"]))
                sh(["git", "commit", "-qam", msg], cwd=wt)
                if not args.no_pr:
                    sh(["git", "push", "-q", "-u", "origin", branch], cwd=wt)
                    print(sh(["gh", "pr", "create", "--head", branch, "--title", msg.splitlines()[0],
                              "--body", msg.split("\n\n", 1)[1]], cwd=wt), flush=True)
                else:
                    print(f"kept on branch {branch} (worktree {wt})", flush=True)
                return 0
            previous = (f"YOUR PREVIOUS EDITS ({json.dumps(proposal['edits'])[:2000]}) were rejected: "
                        f"fixed {fixed or 'nothing'}, broke {broke or 'nothing'}. Try a different change.\n\n")
        print("no change kept", flush=True)
        return 1
    finally:
        if not args.no_pr:
            sh(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO, check=False)


if __name__ == "__main__":
    sys.exit(main())
