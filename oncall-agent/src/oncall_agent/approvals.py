"""Human approval of the agent's proposed change, in the alert's Slack thread.

With ``ONCALL_ACTIONS=approve`` an action tool pauses its Agentspan execution on a HUMAN
task. The listener posts what will change and moves on; every poll it checks the thread
for a reply from an approver:

* ``approve`` -> the HUMAN task is completed with approved=true; the tool runs (ah5r
  workflow, then waits for the rollout) and the agent's final answer is posted.
* ``reject`` (or no answer within 2h) -> approved=false; the server ends the execution.

Only replies from ``ONCALL_APPROVERS`` count; bot messages never do. The decision is
saved before it is sent, so a crash cannot apply it twice.
"""
from __future__ import annotations

import json
import logging
import time

from .actions import describe

log = logging.getLogger(__name__)

APPROVAL_TTL_S = 2 * 3600
EXECUTION_TTL_S = 45 * 60


def extract_calls(pending: dict | None) -> list[tuple[str, dict]]:
    """(tool name, arguments) for each tool call waiting on the HUMAN task."""
    calls = []
    for tc in (pending or {}).get("toolCalls") or []:
        args = tc.get("args") or tc.get("inputParameters") or tc.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"raw": args}
        calls.append((tc.get("name") or tc.get("toolName") or "?", args))
    if not calls and (pending or {}).get("tool_name"):
        calls.append((pending["tool_name"], pending.get("parameters") or {}))
    return calls


def proposal_text(cluster: str, calls: list[tuple[str, dict]], approvers: tuple[str, ...]) -> str:
    summary = next((a.get("triage_summary") for _, a in calls if a.get("triage_summary")), "")
    changes = "\n".join(f"• {describe(n, a)}" for n, a in calls)
    who = " ".join(f"<@{u}>" for u in approvers) or "an approver"
    return (f"{summary}\n\n:raised_hand: *Approval needed* — on `{cluster}` the agent will:\n{changes}\n"
            f"{who}: reply `approve` or `reject` in this thread "
            f"(expires in {APPROVAL_TTL_S // 3600}h).")


def decision(replies: list[dict], approvers: tuple[str, ...], after: float) -> tuple[str, str] | None:
    """First approve/reject reply from an approver posted after the proposal."""
    for m in sorted(replies, key=lambda m: float(m.get("ts", 0))):
        if float(m.get("ts", 0)) <= after or m.get("bot_id") or m.get("user") not in approvers:
            continue
        word = (m.get("text") or "").strip().lower().split()
        if word and word[0] in ("approve", "approved", "reject", "rejected"):
            return ("approve" if word[0].startswith("approve") else "reject"), m["user"]
    return None


def process_pending(cfg, slack, runtime, state: dict, summary_text, save) -> None:
    """Advance every pending approval / approved execution by one step."""
    pending = state.setdefault("pending_actions", {})
    now = time.time()
    for exec_id, p in list(pending.items()):
        channel, thread = p["channel"], p["thread_ts"]
        try:
            if p["phase"] == "awaiting":
                verdict = decision(slack.read_replies(channel, thread), cfg.approvers, p["asked_at"])
                if verdict is None and now - p["asked_at"] > APPROVAL_TTL_S:
                    verdict = ("reject", "expired")
                if verdict is None:
                    continue
                action, user = verdict
                p.update(phase="executing" if action == "approve" else "done", decided_by=user, decided_at=now)
                save()  # recorded before it is sent: never applied twice
                runtime.respond(exec_id, {"approved": action == "approve",
                                          "reason": f"{action} by {user} in Slack"})
                slack.post_reply(channel, thread,
                                 f":white_check_mark: Approved by <@{user}> — applying." if action == "approve"
                                 else (":no_entry: Expired after "
                                       f"{APPROVAL_TTL_S // 3600}h — nothing was changed." if user == "expired"
                                       else f":no_entry: Rejected by <@{user}> — nothing was changed."))
            elif p["phase"] == "executing":
                st = runtime.get_status(exec_id)
                if st.is_complete:
                    try:
                        text = summary_text(st)
                    except Exception as exc:
                        text = f":warning: The change ran but the agent gave no summary: `{exc}`"
                    slack.post_reply(channel, thread,
                                     text if str(st.status).upper() == "COMPLETED"
                                     else f":warning: Change execution ended {st.status} — check `{exec_id}`.")
                    p["phase"] = "done"
                elif now - p["decided_at"] > EXECUTION_TTL_S:
                    slack.post_reply(channel, thread, f":warning: Approved change still running after "
                                                      f"{EXECUTION_TTL_S // 60} min — check `{exec_id}`.")
                    p["phase"] = "done"
        except Exception:  # one broken approval must not stop the others or the poll loop
            log.exception("pending action %s failed", exec_id)
            continue
        if p["phase"] == "done":
            pending.pop(exec_id, None)
        save()
