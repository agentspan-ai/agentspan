"""Capture every triage and the humans' verdict on it — the input of the improvement loop.

* ``triages.jsonl`` — one line per triage: the alert, the agent's answer, any proposed
  change and its approval. The tool calls themselves are in the recordings
  (``ONCALL_RECORD_DIR``, one file per alert execution), so any triage can be replayed.
* ``feedback.jsonl`` — what people said in the alert thread afterwards:
    ``correct`` / ``right`` / ``good`` / ``:white_check_mark:``  -> the cause was right
    ``wrong`` / ``:x:``                                           -> the cause was wrong
    ``cause: <the real cause>``                                   -> wrong, and the truth
    ``action: <what should have been done>``                      -> the right action
    ``? <question>`` or ``@agent <question>``                    -> a follow-up question the agent
                                                                    answers in the thread
  ``scripts/harvest_cases.py`` turns these into eval cases (a question after an answer is a
  sign the answer was not enough).

Threads are watched for ``WATCH_S``; each poll reads at most ``MAX_THREADS_PER_POLL`` of
them (oldest-checked first) to stay inside Slack's rate limits.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

WATCH_S = 3 * 86400
MAX_THREADS_PER_POLL = 15
_CORRECT = re.compile(r"^(?:(?:correct|right|good|accurate)\b|:white_check_mark:|:heavy_check_mark:|✅|👍|:\+1:)", re.I)
_WRONG = re.compile(r"^(wrong|incorrect|:x:|❌|👎|:-1:)", re.I)


def parse(text: str) -> dict | None:
    """A feedback reply's meaning, or None when the message is not feedback."""
    t = (text or "").strip()
    # A verdict comes only from an explicit word; "cause: …" / "action: …" add the truth but are
    # NOT a verdict (seen live 2026-10-29: a teammate explained the cause of an alert the agent had
    # got right, and it was counted as wrong).
    out: dict = {}
    if _CORRECT.match(t):
        out["verdict"] = "correct"
    elif _WRONG.match(t):
        out.update(verdict="wrong", note=t)
    for field in ("cause", "action"):
        m = re.search(rf"\b{field}\s*:\s*(.+?)(?=\n\s*(?:cause|action)\s*:|\Z)", t, re.I | re.S)
        if m:
            out[field] = m.group(1).strip()
    return out or None


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def log_triage(store: Path, record: dict) -> None:
    _append(store / "triages.jsonl", {"at": time.time(), **record})


def watch(state: dict, channel: str, thread_ts: str, alert_execution: str, cluster: str | None,
          answer_posted_at: float) -> None:
    state.setdefault("feedback_watch", {})[thread_ts] = {
        "channel": channel, "alert_execution": alert_execution, "cluster": cluster,
        "after": answer_posted_at, "checked": 0.0, "seen": []}


_DECISION = re.compile(r"^(approve|approved|reject|rejected)\b", re.I)


_ASK = re.compile(r"^(can|could|would|will|please|pls|why|what|how|where|when|which|who|is|are|was|were|"
                  r"do|does|did|should|check|investigate|dig|explain|show|look|find|verify|confirm|tell)\b", re.I)


def is_question(text: str, bot_user_id: str | None) -> bool:
    """A reply addressed to the agent in its own alert thread: it asks something ('?' anywhere),
    reads as a request ('can you…', 'why…', 'investigate…'), or @-mentions the bot. Approvals and
    feedback words are not questions. (The first rule — must START with '?' — missed every real
    question people typed, seen live 2026-10-29.)"""
    t = (text or "").strip()
    if not t or _DECISION.match(t) or parse(t):
        return False
    return "?" in t or bool(_ASK.match(t)) or bool(bot_user_id and f"<@{bot_user_id}>" in t)


def collect(slack, state: dict, store: Path, save, bot_user_id: str | None = None) -> int:
    """Read new human replies in watched threads; record feedback and queue questions."""
    watched = state.setdefault("feedback_watch", {})
    now, found = time.time(), 0
    for thread_ts, w in list(watched.items()):
        if now - w["after"] > WATCH_S:
            watched.pop(thread_ts)
    for thread_ts, w in sorted(watched.items(), key=lambda kv: kv[1]["checked"])[:MAX_THREADS_PER_POLL]:
        w["checked"] = now
        try:
            replies = slack.read_replies(w["channel"], thread_ts)
        except Exception:
            log.exception("feedback read failed for thread %s", thread_ts)
            continue
        for m in replies:
            ts = m.get("ts", "0")
            if float(ts) <= w["after"] or m.get("bot_id") or ts in w["seen"]:
                continue
            w["seen"].append(ts)
            if is_question(m.get("text", ""), bot_user_id):
                state.setdefault("questions", []).append({
                    "channel": w["channel"], "thread_ts": thread_ts, "alert_execution": w["alert_execution"],
                    "cluster": w["cluster"], "user": m.get("user"), "ts": ts, "text": m.get("text", "")})
                _append(store / "feedback.jsonl", {"at": now, "alert_execution": w["alert_execution"],
                                                    "cluster": w["cluster"], "by": m.get("user"), "msg_ts": ts,
                                                    "question": m.get("text", "")})
                found += 1
                continue
            meaning = parse(m.get("text", ""))
            if not meaning:
                continue
            _append(store / "feedback.jsonl", {"at": now, "alert_execution": w["alert_execution"],
                                                "cluster": w["cluster"], "by": m.get("user"), "msg_ts": ts,
                                                **meaning})
            found += 1
            try:
                slack.post_reply(w["channel"], thread_ts,
                                 ":memo: Noted — this incident becomes an eval case for the agent.")
            except Exception:
                log.exception("feedback ack failed")
    if found or watched:
        save()
    return found
