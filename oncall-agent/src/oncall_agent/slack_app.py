"""Slack polling: read the alert channel, triage each new alert, reply in-thread.

Mirrors the repo's Slack convention (sdk/python/examples/91_slack_autofix_agent.py):
plain Web API calls with a bot token (no Socket Mode), run-once or ``--loop``, and
dedup via a local state file. Slack I/O lives here — the triage agent stays pure and
only investigates a given execution id.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

import requests
from conductor.ai.agents import AgentRuntime

from . import approvals, feedback
from .agent import INSTRUCTIONS, build_agent
from .alert import Alert, alert_signature, message_text, pagerduty_cluster, parse_alert, signable_text
from .config import Config
from .runtime_compat import TriageIncomplete, answer_text, summary_text
from .worker_health import CRITICAL_TASK_TYPES, evaluate

log = logging.getLogger("oncall_agent")
_SLACK_API = "https://slack.com/api"
_POLL_LIMIT = 20
# One incident = one triage per window, across channels. The raw channel fires
# the same incident every ~5 min with a fresh execution id; without this, each
# firing got a full LLM triage (seen live: 4x shailesh-test-gcp in <1h).
_SIGNATURE_COOLDOWN_S = int(os.environ.get("ONCALL_SIGNATURE_COOLDOWN", "3600"))
# Incident memory: between full triages, repeat firings get a deterministic
# in-thread update built from the remembered diagnosis — zero LLM tokens. A
# full re-investigation runs only this often (or when the signature changes,
# e.g. severity escalation / new issue set, which bypasses memory by design).
_FULL_TRIAGE_INTERVAL_S = int(os.environ.get("ONCALL_FULL_TRIAGE_INTERVAL", "21600"))
# Wall-clock cap on a single triage. runtime.run() blocks, so a triage that never
# finishes wedges the whole poll loop — no alert is looked at again until the
# process is restarted (seen live: a tool task hit its responseTimeout, was
# re-queued, nobody polled it, and the loop sat on one incident from Sat 01:25
# to Mon 12:48 — 59h, zero triages). The SDK's own ``timeout`` is not a
# wall-clock bound: _poll_status_until_complete increments elapsed by 1 per
# iteration while each iteration also does a network call, so under connection
# churn it drifts arbitrarily far behind real time. Hence the deadline here.
_TRIAGE_DEADLINE_S = int(os.environ.get("ONCALL_TRIAGE_DEADLINE", "1800"))


class _NotRemembered(Exception):
    """Internal: skip storing a diagnosis in incident memory."""


class TriageTimeout(Exception):
    """A single triage exceeded :data:`_TRIAGE_DEADLINE_S` wall-clock seconds."""


class _AwaitingApproval(Exception):
    """The agent proposed a change and its execution is paused on a HUMAN task."""

    def __init__(self, execution_id: str, pending: dict | None):
        super().__init__(execution_id)
        self.execution_id, self.pending = execution_id, pending or {}


def _start_until_answer(runtime: AgentRuntime, agent, prompt: str, deadline_s: int):
    """Like _run_with_deadline, but returns control when the agent pauses for approval
    instead of blocking the poll loop on a human (ONCALL_ACTIONS=approve)."""
    handle = runtime.start(agent, prompt)
    end = time.time() + deadline_s
    while time.time() < end:
        st = runtime.get_status(handle.execution_id)
        if st.is_waiting:
            raise _AwaitingApproval(handle.execution_id, st.pending_tool)
        if st.is_complete:
            if str(st.status).upper() != "COMPLETED":
                raise TriageIncomplete(f"agent run ended {st.status}")
            return st
        time.sleep(5)
    raise TriageTimeout(f"triage exceeded {deadline_s}s and was abandoned")


def _run_with_deadline(runtime: AgentRuntime, agent, prompt: str, deadline_s: int):
    """Run the agent, giving up after ``deadline_s`` wall-clock seconds.

    The call runs on a daemon thread so the poll loop can walk away from it: a
    Python thread cannot be killed, but the loop must not be held hostage by
    one wedged execution. The orphan is left polling — the SDK's ``timeout`` is
    passed down but is not a wall-clock bound, so in the worst case it never
    exits. That is a slow leak, not a wedge: it holds nothing the loop needs.
    """
    box: dict = {}

    def _target() -> None:
        try:
            box["result"] = runtime.run(agent, prompt, timeout=deadline_s)
        except BaseException as exc:  # re-raised on the caller's thread below
            box["error"] = exc

    worker = threading.Thread(
        target=_target, name="oncall-triage", daemon=True
    )
    worker.start()
    worker.join(deadline_s)
    if worker.is_alive():
        raise TriageTimeout(f"triage exceeded {deadline_s}s and was abandoned")
    if "error" in box:
        raise box["error"]
    result = box["result"]
    # A FAILED/TERMINATED execution is not an exception — run() returns
    # normally and summary_text() falls through to str(output). That is how
    # `{'result': None, 'finishReason': 'TOOL_CALLS', ...}` got posted into a
    # prod thread and written to incident memory as a diagnosis when the
    # 59h-wedged execution was terminated by hand. A non-COMPLETED run has no
    # diagnosis in it; treat it as the failure it is.
    status = getattr(result, "status", None)
    if status is not None and status != "COMPLETED":
        raise TriageIncomplete(
            f"agent execution {status}"
            + (f": {getattr(result, 'error', None)}" if getattr(result, "error", None) else "")
        )
    return result



def _poll_ages(server_url: str, task_types) -> dict:
    """Seconds since each task type was last polled; None when no poller exists."""
    ages: dict = {}
    base = (server_url or "").rstrip("/")
    for tt in task_types:
        try:
            r = requests.get(f"{base}/tasks/queue/polldata", params={"taskType": tt}, timeout=8)
            rows = r.json() if r.ok else []
            if not rows:
                ages[tt] = None
                continue
            newest = max(int(x.get("lastPollTime") or 0) for x in rows)
            ages[tt] = max(0.0, time.time() - newest / 1000.0) if newest else None
        except Exception:
            # Cannot tell — do NOT report dead on a transient probe failure.
            ages[tt] = 0.0
    return ages


class SlackClient:
    """Minimal Slack Web API client: read channel history, post threaded replies."""

    def __init__(self, bot_token: str):
        self._token = bot_token

    def read_messages(self, channel: str, oldest: str = "0", limit: int = _POLL_LIMIT) -> list[dict]:
        """Every message newer than ``oldest`` — paged, so a burst larger than one page
        (alerts pile up while a triage blocks the loop) is not silently skipped."""
        out, cursor = [], None
        for _ in range(50):
            params = {"channel": channel, "oldest": oldest, "limit": max(limit, 100)}
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(
                f"{_SLACK_API}/conversations.history",
                headers={"Authorization": f"Bearer {self._token}"},
                params=params,
                timeout=30,
            )
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"conversations.history failed: {data.get('error')}")
            out += [m for m in data.get("messages", []) if m.get("type") == "message"]
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not data.get("has_more") or not cursor:
                break
        return out

    def bot_user_id(self) -> str | None:
        """The bot's own user id (people @-mention it to ask a follow-up question)."""
        if not hasattr(self, "_bot_uid"):
            try:
                data = requests.get(f"{_SLACK_API}/auth.test",
                                    headers={"Authorization": f"Bearer {self._token}"}, timeout=30).json()
                self._bot_uid = data.get("user_id") if data.get("ok") else None
            except Exception:
                return None
        return self._bot_uid

    def read_replies(self, channel: str, thread_ts: str) -> list[dict]:
        """Every message in one thread (the parent included)."""
        resp = requests.get(
            f"{_SLACK_API}/conversations.replies",
            headers={"Authorization": f"Bearer {self._token}"},
            params={"channel": channel, "ts": thread_ts, "limit": 200},
            timeout=30,
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"conversations.replies failed: {data.get('error')}")
        return data.get("messages", [])

    def post_reply(self, channel: str, thread_ts: str, text: str) -> None:
        resp = requests.post(
            f"{_SLACK_API}/chat.postMessage",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            json={"channel": channel, "thread_ts": thread_ts, "text": text},
            timeout=30,
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"chat.postMessage failed: {data.get('error')}")


_LEGACY_STATE = Path("/tmp/oncall_agent_state.json")
_LOCK_FD = None


def _load_state(path: Path) -> dict:
    """Load state; on a missing or corrupt file start from NOW, never from Slack's
    beginning (that re-triaged the channel's history into old threads)."""
    for candidate in (path, _LEGACY_STATE):
        if candidate.exists():
            try:
                return json.loads(candidate.read_text())
            except Exception:
                log.error("state file %s unreadable; starting fresh from now", candidate)
                break
    return {"last_ts": None, "processed": [], "started_at": time.time()}


def _save_state(path: Path, state: dict) -> None:
    """Atomic write: a crash mid-write must not leave a truncated file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, path)


def _acquire_single_instance_lock(path: Path) -> None:
    """Two listeners would overwrite each other's state and double-post; refuse to run twice."""
    import fcntl
    global _LOCK_FD
    if _LOCK_FD is not None:  # already held by this process (run_once runs every poll)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _LOCK_FD = open(path.with_suffix(".lock"), "w")
    try:
        fcntl.flock(_LOCK_FD, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(f"another on-call listener holds {path.with_suffix('.lock')}; exiting")


def _triage_prompt(alert: Alert, prior: dict | None = None) -> str:
    prompt = (
        "A cluster health-check alert fired.\n\n"
        f"Alert text:\n{alert.raw}\n\n"
        f"The failing health_check execution id is: {alert.execution_id}\n"
    )
    if prior:
        age_h = (time.time() - prior.get("last_full_ts", 0)) / 3600
        prompt += (
            f"\nPRIOR DIAGNOSIS from your last full investigation (~{age_h:.0f}h ago, "
            f"{prior.get('firings', 1)} firings since first seen):\n{prior.get('summary', '')}\n\n"
            "VERIFY whether this diagnosis still holds and report the DELTA (metrics "
            "moved? new failure mode?) rather than rediscovering from scratch — keep "
            "the investigation to the few reads that confirm or refute it.\n"
        )
    try:
        from .kb import leads_for_alert
        prompt += leads_for_alert(alert.raw, alert.cluster)
    except Exception:  # the knowledge base must never break a triage
        log.exception("knowledge-base lookup failed")
    prompt += "Investigate (read-only) and produce the triage summary."
    return prompt


def _root_cause_excerpt(summary: str, limit: int = 700) -> str:
    """The *Likely root cause* section of a triage summary, for incident memory."""
    marker = summary.find("*Likely root cause*")
    if marker < 0:
        return summary[:limit]
    end = summary.find("*Suggested next step*", marker)
    excerpt = summary[marker : end if end > 0 else None].strip()
    return excerpt[:limit]


_PLAYBOOK_VERSION = __import__("hashlib").sha1(INSTRUCTIONS.encode()).hexdigest()[:12]


def _same_incident(prior: dict, execution_id: str) -> bool:
    """True when this firing continues the incident the stored diagnosis was written for."""
    if prior.get("playbook") != _PLAYBOOK_VERSION:
        return False
    try:
        from .tools import _disp
        ctx = _disp().get_context(execution_id)
        info = _disp().alert_info(execution_id)
        if not info["alert_ms"] or not ctx.get("clusterId"):
            return False
        onset_ms = _disp().failing_since(ctx.get("clusterId"), info["alert_ms"], info["issues"])
    except Exception:
        return False
    return onset_ms <= prior.get("last_full_ts", 0) * 1000


def _memory_update_text(cfg: Config, prior: dict, now: float) -> str:
    age_h = (now - prior.get("last_full_ts", now)) / 3600
    first_h = (now - prior.get("first_seen", now)) / 3600
    return (
        f"{_header(cfg)}"
        f":brain: *Known ongoing incident* — same signature as the diagnosis from "
        f"~{age_h:.1f}h ago ({prior.get('firings', 1)} firings over ~{first_h:.1f}h). "
        f"Reply built from incident memory; no new investigation was run.\n\n"
        f"{prior.get('summary', '')}\n\n"
        f"_Next full re-investigation after "
        f"{_FULL_TRIAGE_INTERVAL_S // 3600}h, or immediately if the alert changes "
        f"(severity / issue set)._"
    )


def _header(cfg: Config) -> str:
    if cfg.actions == "approve":
        return "*:robot_face: On-call triage* _(read-only; any change waits for your approval)_\n"
    return (
        "*:robot_face: On-call triage (dry-run · read-only)*\n"
        if cfg.dry_run
        else "*:robot_face: On-call triage*\n"
    )


# Measurement trial (features frozen 2026-10-28 -> 2026-11-11): every answer asks for a verdict.
_FEEDBACK_ASK = ("\n_Was this right? Reply `correct` or `wrong` — add `cause: <real cause>` if you know it. "
                 "We are measuring the agent's accuracy._")


def _store(cfg: Config) -> Path:
    return Path(cfg.state_file).parent


def _capture(cfg: Config, state: dict, channel: str, ts: str, alert, cluster, msg, answer: str,
             agent_execution: str | None = None) -> None:
    """Log the triage and watch its thread for feedback (the improvement loop's input)."""
    try:
        feedback.log_triage(_store(cfg), {
            "alert_execution": alert.execution_id, "cluster": alert.cluster or cluster,
            "alert_text": message_text(msg), "answer": answer, "agent_execution": agent_execution,
            "channel": channel, "thread_ts": ts, "model": cfg.model, "playbook": _PLAYBOOK_VERSION})
        feedback.watch(state, channel, ts, alert.execution_id, alert.cluster or cluster, time.time())
    except Exception:  # capture must never break triage
        log.exception("triage capture failed")


def _channel_state(state: dict, channel: str, cfg: Config) -> dict:
    """Per-channel dedup state, migrating the legacy single-channel shape
    (top-level last_ts/processed) onto the first configured channel."""
    channels = state.setdefault("channels", {})
    if channel not in channels:
        legacy = {}
        if channel == cfg.slack_alert_channels[0] and state.get("last_ts"):
            legacy = {"last_ts": state.get("last_ts"), "processed": state.get("processed") or []}
        # A newly watched channel starts from NOW: its history is old alerts (seen live
        # 2026-10-28: adding a channel began triaging April alerts into their old threads).
        channels[channel] = legacy or {"last_ts": f"{time.time():.6f}", "processed": []}
    return channels[channel]


def _poll_channel(cfg: Config, slack: SlackClient, runtime: AgentRuntime, agent,
                  channel: str, state: dict, state_path: Path) -> int:
    ch_state = _channel_state(state, channel, cfg)
    processed = set(ch_state.get("processed") or [])

    # Slack returns newest-first; process oldest-first so the window advances cleanly.
    messages = slack.read_messages(
        channel, oldest=ch_state.get("last_ts") or str(state.get("started_at") or "0"), limit=_POLL_LIMIT
    )
    messages.sort(key=lambda m: float(m["ts"]))

    handled = 0
    for msg in messages:
        ts = msg["ts"]
        if ts in processed:
            continue
        # Only alerts posted by bots (health-check notifier, PagerDuty) start a triage — a
        # person pasting an execution link into the channel must not.
        from_bot = bool(msg.get("bot_id") or msg.get("subtype") == "bot_message")
        alert = parse_alert(message_text(msg)) if from_bot else None
        pd_resolved = (msg.get("metadata") or {}).get("event_type") == "incident_resolved" \
            or (msg.get("text") or "").startswith(":large_green_circle:")
        if not alert and from_bot and not pd_resolved and (cluster := pagerduty_cluster(message_text(msg))):
            from .tools import _disp
            exec_id = _disp().latest_failed_health_check(cluster, int(float(ts) * 1000))
            if exec_id:
                alert = Alert(execution_id=exec_id, severity=None, cluster=cluster,
                              organization=None, raw=message_text(msg))
            elif time.time() - float(ts) < 600:
                # The search index can lag the page by minutes: stop here and retry this
                # message next poll instead of marking it processed and losing it.
                log.info("page for %s not resolvable yet; retrying next poll", cluster)
                break
            else:
                log.warning("page for %s matched no failed health_check", cluster)
                slack.post_reply(channel, ts, f":grey_question: Couldn't match this page to a failed "
                                              f"health check for `{cluster}` in the 30 min before it — needs a human.")
        if alert:
            now = time.time()
            # An execution id, once triaged, is never triaged again — the raw
            # channel and the digest channel carry the SAME execution in texts
            # that tokenize differently, so the signature layer alone misses
            # that pair (seen live 2026-07-22).
            executions = state.setdefault("executions", {})
            # The cluster goes in verbatim: the token filter drops digit-bearing words, so
            # "vantaca-stage1" and "vantaca-stage2" would otherwise share one signature.
            sig_cluster = alert.cluster
            if not sig_cluster:
                try:
                    from .tools import _disp
                    sig_cluster = _disp().get_context(alert.execution_id).get("clusterName")
                except Exception:
                    sig_cluster = None
            sig = f"{sig_cluster or '?'}|" + alert_signature(signable_text(message_text(msg)))
            signatures = state.setdefault("signatures", {})
            last = signatures.get(sig)
            if alert.execution_id in executions or (
                last is not None and (now - last) < _SIGNATURE_COOLDOWN_S
            ):
                log.info(
                    "skip duplicate (exec_seen=%s, sig_age=%s) channel=%s exec=%s",
                    alert.execution_id in executions,
                    f"{now - last:.0f}s" if last is not None else "none",
                    channel, alert.execution_id,
                )
                processed.add(ts)
                ch_state["processed"] = list(processed)[-500:]
                ch_state["last_ts"] = ts
                _save_state(state_path, state)
                continue
            signatures[sig] = now
            executions[alert.execution_id] = now
            if len(executions) > 500:  # keep the newest 500
                state["executions"] = dict(
                    sorted(executions.items(), key=lambda kv: kv[1])[-500:]
                )
            # prune expired entries so the state file stays small
            state["signatures"] = {
                s: t for s, t in signatures.items() if (now - t) < _SIGNATURE_COOLDOWN_S * 4
            }
            # Persist the arm BEFORE the multi-minute triage: an exception that
            # escapes mid-triage (e.g. a failed Slack post) is absorbed by the
            # per-channel guard and would otherwise discard the in-memory arm —
            # later firings of the same incident then re-triage (seen live).
            _save_state(state_path, state)

            # Incident memory: a known ongoing incident gets a deterministic
            # update from the remembered diagnosis — no LLM tokens burned.
            incidents = state.setdefault("incidents", {})
            prior = incidents.get(sig)
            # Reuse a diagnosis only for the SAME incident: written by the current playbook,
            # and the cluster has failed continuously since — a clean check in between means
            # a new incident (seen live 2026-10-27: a stale wrong diagnosis was replayed).
            if prior and not _same_incident(prior, alert.execution_id):
                prior = None
            if prior and (now - prior.get("last_full_ts", 0)) < _FULL_TRIAGE_INTERVAL_S:
                log.info("memory update (no LLM) channel=%s exec=%s firings=%d",
                         channel, alert.execution_id, prior.get("firings", 0) + 1)
                prior["firings"] = prior.get("firings", 1) + 1
                slack.post_reply(channel, ts, _memory_update_text(cfg, prior, now))
                handled += 1
                processed.add(ts)
                ch_state["processed"] = list(processed)[-500:]
                ch_state["last_ts"] = ts
                _save_state(state_path, state)
                continue

            # PREFLIGHT: are our own tool workers alive? Twice the process stayed up
            # while SDK worker threads died, so every triage forked tool tasks nothing
            # would ever claim and burned the full deadline producing nothing (2.1 days,
            # 26+ dead triages). A guard inside the tool cannot help — the tool never
            # runs. Checking here turns a silent 30-minute timeout into an instant,
            # accurate finding.
            health = evaluate(_poll_ages(cfg.agentspan_server_url, CRITICAL_TASK_TYPES))
            if not health["ok"]:
                log.error("SKIPPING triage channel=%s exec=%s — %s",
                          channel, alert.execution_id, health["reason"])
                slack.post_reply(
                    channel, ts,
                    f":warning: Triage skipped — on-call agent tool workers are not "
                    f"polling. {health['reason']}",
                )
                handled += 1
                processed.add(ts)
                ch_state["processed"] = list(processed)[-500:]
                ch_state["last_ts"] = ts
                _save_state(state_path, state)
                continue

            log.info("triage channel=%s exec=%s cluster=%s sev=%s",
                     channel, alert.execution_id, alert.cluster, alert.severity)
            try:
                slack.post_reply(
                    channel,
                    ts,
                    f":mag: On-call triage starting for execution `{alert.execution_id}`…",
                )
            except Exception:
                # Un-mark so the next poll retries this alert instead of skipping it as seen.
                state.get("executions", {}).pop(alert.execution_id, None)
                if last is None:
                    state.get("signatures", {}).pop(sig, None)
                else:
                    state.setdefault("signatures", {})[sig] = last
                _save_state(state_path, state)
                raise
            try:
                result = (_start_until_answer if cfg.actions == "approve" else _run_with_deadline)(
                    runtime, agent, _triage_prompt(alert, prior), _TRIAGE_DEADLINE_S
                )
                summary = summary_text(result)
                slack.post_reply(channel, ts, _header(cfg) + summary + _FEEDBACK_ASK)
                _capture(cfg, state, channel, ts, alert, sig_cluster, msg, answer=summary)
                if summary.lower().startswith("*cause*: unknown"):
                    raise _NotRemembered()
                incidents[sig] = {
                    "summary": _root_cause_excerpt(summary),
                    "playbook": _PLAYBOOK_VERSION,
                    "last_full_ts": now,
                    "first_seen": (prior or {}).get("first_seen", now),
                    "firings": (prior or {}).get("firings", 0) + 1,
                }
                if len(incidents) > 200:  # keep the most recently investigated
                    state["incidents"] = dict(
                        sorted(incidents.items(), key=lambda kv: kv[1]["last_full_ts"])[-200:]
                    )
            except _NotRemembered:  # posted, but an "unknown" cause is not worth replaying
                pass
            except _AwaitingApproval as wait:  # the change waits for a human; the loop moves on
                calls = approvals.extract_calls(wait.pending)
                slack.post_reply(channel, ts, _header(cfg) + approvals.proposal_text(
                    alert.cluster or sig_cluster or "?", calls, cfg.approvers))
                state.setdefault("pending_actions", {})[wait.execution_id] = {
                    "channel": channel, "thread_ts": ts, "phase": "awaiting", "asked_at": time.time(),
                    "alert_execution": alert.execution_id, "calls": [[n, a] for n, a in calls]}
                _capture(cfg, state, channel, ts, alert, sig_cluster, msg,
                         answer=approvals.proposal_text("", calls, ()), agent_execution=wait.execution_id)
                log.info("awaiting approval channel=%s exec=%s calls=%s", channel, wait.execution_id,
                         [n for n, _ in calls])
            except TriageIncomplete as exc:  # never post or remember a non-answer
                state.get("signatures", {}).pop(sig, None)  # let the next firing get a real triage
                log.error("triage incomplete channel=%s exec=%s: %s", channel, alert.execution_id, exc)
                slack.post_reply(channel, ts, ":warning: Triage ended without a conclusion — needs a human.")
            except TriageTimeout as exc:  # abandon this incident, keep polling
                state.get("signatures", {}).pop(sig, None)  # no cooldown for a triage that never finished
                log.error("triage timed out channel=%s exec=%s: %s",
                          channel, alert.execution_id, exc)
                slack.post_reply(
                    channel, ts,
                    f":hourglass_flowing_sand: Triage gave up after "
                    f"{_TRIAGE_DEADLINE_S}s — `{alert.execution_id}` needs a human.",
                )
            except Exception as exc:  # surface into the thread, keep polling
                state.get("signatures", {}).pop(sig, None)
                log.exception("triage failed")
                slack.post_reply(channel, ts, f":warning: Triage failed: `{exc}`")
            handled += 1

        processed.add(ts)
        ch_state["processed"] = list(processed)[-500:]  # cap unbounded growth
        ch_state["last_ts"] = ts
        _save_state(state_path, state)

    return handled


_MAX_QUESTIONS_PER_POLL = 3
_THREAD_CHARS = 6000


def _followup_prompt(q: dict, thread: list[dict]) -> str:
    lines = []
    for m in sorted(thread, key=lambda m: float(m.get("ts", 0))):
        who = "agent" if m.get("bot_id") else "engineer"
        lines.append(f"[{who}] {(m.get('text') or '').strip()}")
    transcript = "\n".join(lines)[-_THREAD_CHARS:]
    prior = _prior_findings(q["alert_execution"])
    return (f"FOLLOW-UP QUESTION in the thread of the alert whose failing health_check execution id is "
            f"{q['alert_execution']} (cluster {q.get('cluster') or '?'}).\n\n"
            f"Thread so far (oldest first; the first message is the alert):\n{transcript}\n\n"
            + (f"PRIOR FINDINGS (tool results from your earlier investigation of this alert):\n{prior}\n\n"
               if prior else "")
            + f"The engineer now asks:\n{q['text']}\n\nAnswer that question.")


_PRIOR_CHARS = 8000


def _prior_findings(alert_execution: str, per_call: int = 900) -> str:
    """What the earlier triage of this alert already read, from its recording (newest call per tool+args)."""
    rec_dir = os.environ.get("ONCALL_RECORD_DIR")
    path = Path(rec_dir) / f"{alert_execution}.jsonl" if rec_dir else None
    if not path or not path.exists():
        return ""
    latest: dict[str, str] = {}
    for line in path.read_text().splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        args = {k: v for k, v in (c.get("args") or {}).items() if k != "execution_id"}
        body = json.dumps(c.get("result", c.get("error")), default=str)[:per_call]
        latest[f"{c.get('tool')}({args})"] = body
    return "\n".join(f"- {k} -> {v}" for k, v in latest.items())[-_PRIOR_CHARS:]


def _answer_questions(cfg: Config, slack, runtime, agent, state: dict, save) -> None:
    """Answer queued thread questions, a few per poll, each with the full thread as context."""
    queue = state.get("questions") or []
    for q in queue[:_MAX_QUESTIONS_PER_POLL]:
        queue.remove(q)
        save()  # dequeued before answering: a crash never answers twice
        try:
            thread = slack.read_replies(q["channel"], q["thread_ts"])
            result = (_start_until_answer if cfg.actions == "approve" else _run_with_deadline)(
                runtime, agent, _followup_prompt(q, thread), _TRIAGE_DEADLINE_S)
            text = answer_text(result)
            slack.post_reply(q["channel"], q["thread_ts"], f"<@{q['user']}> {text}")
            feedback.log_triage(_store(cfg), {"followup": q, "answer": text})
        except _AwaitingApproval as wait:
            calls = approvals.extract_calls(wait.pending)
            slack.post_reply(q["channel"], q["thread_ts"],
                             approvals.proposal_text(q.get("cluster") or "?", calls, cfg.approvers))
            state.setdefault("pending_actions", {})[wait.execution_id] = {
                "channel": q["channel"], "thread_ts": q["thread_ts"], "phase": "awaiting",
                "asked_at": time.time(), "alert_execution": q["alert_execution"],
                "calls": [[n, a] for n, a in calls]}
        except Exception as exc:
            log.exception("follow-up failed")
            try:
                slack.post_reply(q["channel"], q["thread_ts"], f":warning: Could not answer: `{exc}`")
            except Exception:
                pass
        save()


def run_once(cfg: Config, slack: SlackClient, runtime: AgentRuntime, agent) -> int:
    """Process new messages in every configured channel once. Returns alerts triaged."""
    state_path = Path(cfg.state_file)
    _acquire_single_instance_lock(state_path)
    state = _load_state(state_path)
    if state.get("pending_actions"):
        approvals.process_pending(cfg, slack, runtime, state, summary_text,
                                  lambda: _save_state(state_path, state),
                                  record=lambda r: feedback.log_triage(_store(cfg), {"approval": r}))
    if state.get("feedback_watch"):
        feedback.collect(slack, state, _store(cfg), lambda: _save_state(state_path, state),
                         bot_user_id=slack.bot_user_id() if hasattr(slack, "bot_user_id") else None)
    if state.get("questions"):
        _answer_questions(cfg, slack, runtime, agent, state, lambda: _save_state(state_path, state))
    handled = 0
    for channel in cfg.slack_alert_channels:
        try:
            handled += _poll_channel(cfg, slack, runtime, agent, channel, state, state_path)
        except Exception:  # one bad channel must not starve the other
            log.exception("poll failed for channel %s", channel)
    return handled


def run(cfg: Config | None = None, loop: bool = False, interval: int | None = None) -> None:
    cfg = cfg or Config.from_env()
    logging.basicConfig(level=logging.INFO)
    from .runtime_compat import use_thread_workers_if_needed

    use_thread_workers_if_needed()
    # Record every live triage's tool calls so any incident can be replayed as an eval case.
    os.environ.setdefault("ONCALL_RECORD_DIR", str(_store(cfg) / "recordings"))
    if not cfg.slack_alert_channels:
        raise SystemExit(
            "SLACK_ALERT_CHANNEL is required (channel id to poll; comma-separate for several)."
        )
    interval = interval or cfg.poll_interval
    slack = SlackClient(cfg.slack_bot_token)

    with AgentRuntime(server_url=cfg.agentspan_server_url) as runtime:
        agent = build_agent(cfg.model, cfg.actions)
        log.info(
            "on-call agent polling channels=%s (loop=%s, interval=%ss, dry_run=%s, model=%s)",
            ",".join(cfg.slack_alert_channels), loop, interval, cfg.dry_run, cfg.model,
        )
        if not loop:
            log.info("handled %d alert(s)", run_once(cfg, slack, runtime, agent))
            return
        while True:
            try:
                handled = run_once(cfg, slack, runtime, agent)
                if handled:
                    log.info("handled %d alert(s)", handled)
            except Exception:
                log.exception("poll cycle failed")
            time.sleep(interval)
