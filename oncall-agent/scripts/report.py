"""How is the on-call agent doing? A short report from what the listener captured.

    PYTHONPATH=src .venv/bin/python scripts/report.py [--days 7] [--store ~/.oncall-agent]

Accuracy counts only triages someone judged (correct vs wrong / corrected cause); the
share of triages with ANY feedback is reported next to it so a high accuracy on three
votes is not mistaken for a measurement.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path


def _rows(path: Path, since: float) -> list[dict]:
    if not path.exists():
        return []
    return [r for r in map(json.loads, path.read_text().splitlines()) if r.get("at", 0) >= since]


def build(store: Path, days: int, now: float | None = None) -> dict:
    since = (now or time.time()) - days * 86400
    triages = _rows(store / "triages.jsonl", since)
    feedback = _rows(store / "feedback.jsonl", since)
    answers = [t for t in triages if t.get("answer") and not t.get("followup")]
    verdicts: dict[str, str] = {}
    for f in feedback:
        if f.get("verdict"):
            verdicts[f["alert_execution"]] = f["verdict"]
    judged = Counter(verdicts.values())
    approvals = Counter(t["approval"].get("outcome", "?") for t in triages if t.get("approval"))
    unknown = sum(1 for t in answers if t["answer"].lower().startswith("*cause*: unknown"))
    clusters = Counter(t.get("cluster") for t in answers).most_common(5)
    return {
        "days": days, "triages": len(answers), "causeUnknown": unknown,
        "withFeedback": len(verdicts), "correct": judged["correct"], "wrong": judged["wrong"],
        "accuracy": round(judged["correct"] / (judged["correct"] + judged["wrong"]), 2)
        if judged["correct"] + judged["wrong"] else None,
        "followUpQuestions": sum(1 for f in feedback if f.get("question")),
        "changesProposed": sum(1 for t in answers if "Approval needed" in t["answer"] or "will:" in t["answer"]),
        "approvalOutcomes": dict(approvals), "topClusters": clusters,
    }


def render(r: dict) -> str:
    acc = f"{r['accuracy']:.0%}" if r["accuracy"] is not None else "n/a"
    return (f"*On-call agent — last {r['days']}d*\n"
            f"• {r['triages']} triages ({r['causeUnknown']} with cause unknown)\n"
            f"• judged {r['withFeedback']}: {r['correct']} correct / {r['wrong']} wrong → accuracy {acc}\n"
            f"• {r['followUpQuestions']} follow-up questions · {r['changesProposed']} changes proposed\n"
            f"• busiest: {', '.join(f'{c} ({n})' for c, n in r['topClusters']) or '-'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--store", default=os.path.expanduser("~/.oncall-agent"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--post-dm", action="store_true", help="also send it to the first approver's Slack DM")
    a = ap.parse_args()
    r = build(Path(a.store), a.days)
    print(json.dumps(r, indent=1) if a.json else render(r))
    if a.post_dm:
        post_dm(render(r))
    return 0


def post_dm(text: str) -> None:
    import requests
    from oncall_agent.config import Config
    cfg = Config.from_env()
    if not cfg.approvers:
        raise SystemExit("ONCALL_APPROVERS is empty: nobody to send the report to")
    h = {"Authorization": f"Bearer {cfg.slack_bot_token}"}
    ch = requests.post("https://slack.com/api/conversations.open", headers=h,
                       json={"users": cfg.approvers[0]}, timeout=30).json()["channel"]["id"]
    r = requests.post("https://slack.com/api/chat.postMessage", headers=h,
                      json={"channel": ch, "text": text}, timeout=30).json()
    if not r.get("ok"):
        raise SystemExit(f"report post failed: {r.get('error')}")


if __name__ == "__main__":
    raise SystemExit(main())
