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

from .agent import build_agent
from .alert import Alert, alert_signature, message_text, parse_alert, signable_text
from .config import Config
from .runtime_compat import summary_text

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


class TriageTimeout(Exception):
    """A single triage exceeded :data:`_TRIAGE_DEADLINE_S` wall-clock seconds."""


class TriageIncomplete(Exception):
    """The agent execution ended FAILED/TERMINATED — no diagnosis to report."""


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


class SlackClient:
    """Minimal Slack Web API client: read channel history, post threaded replies."""

    def __init__(self, bot_token: str):
        self._token = bot_token

    def read_messages(self, channel: str, oldest: str = "0", limit: int = _POLL_LIMIT) -> list[dict]:
        resp = requests.get(
            f"{_SLACK_API}/conversations.history",
            headers={"Authorization": f"Bearer {self._token}"},
            params={"channel": channel, "oldest": oldest, "limit": limit},
            timeout=30,
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"conversations.history failed: {data.get('error')}")
        return [m for m in data.get("messages", []) if m.get("type") == "message"]

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


def _load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"last_ts": None, "processed": []}


def _save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2))


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
    return (
        "*:robot_face: On-call triage (dry-run · read-only)*\n"
        if cfg.dry_run
        else "*:robot_face: On-call triage*\n"
    )


def _channel_state(state: dict, channel: str, cfg: Config) -> dict:
    """Per-channel dedup state, migrating the legacy single-channel shape
    (top-level last_ts/processed) onto the first configured channel."""
    channels = state.setdefault("channels", {})
    if channel not in channels:
        legacy = {}
        if channel == cfg.slack_alert_channels[0] and state.get("last_ts"):
            legacy = {"last_ts": state.get("last_ts"), "processed": state.get("processed") or []}
        channels[channel] = legacy or {"last_ts": None, "processed": []}
    return channels[channel]


def _poll_channel(cfg: Config, slack: SlackClient, runtime: AgentRuntime, agent,
                  channel: str, state: dict, state_path: Path) -> int:
    ch_state = _channel_state(state, channel, cfg)
    processed = set(ch_state.get("processed") or [])

    # Slack returns newest-first; process oldest-first so the window advances cleanly.
    messages = slack.read_messages(
        channel, oldest=ch_state.get("last_ts") or "0", limit=_POLL_LIMIT
    )
    messages.sort(key=lambda m: float(m["ts"]))

    handled = 0
    for msg in messages:
        ts = msg["ts"]
        if ts in processed:
            continue
        alert = parse_alert(message_text(msg))
        if alert:
            now = time.time()
            # An execution id, once triaged, is never triaged again — the raw
            # channel and the digest channel carry the SAME execution in texts
            # that tokenize differently, so the signature layer alone misses
            # that pair (seen live 2026-07-22).
            executions = state.setdefault("executions", {})
            sig = alert_signature(signable_text(message_text(msg)))
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

            log.info("triage channel=%s exec=%s cluster=%s sev=%s",
                     channel, alert.execution_id, alert.cluster, alert.severity)
            slack.post_reply(
                channel,
                ts,
                f":mag: On-call triage starting for execution `{alert.execution_id}`…",
            )
            try:
                result = _run_with_deadline(
                    runtime, agent, _triage_prompt(alert, prior), _TRIAGE_DEADLINE_S
                )
                summary = summary_text(result)
                slack.post_reply(channel, ts, _header(cfg) + summary)
                incidents[sig] = {
                    "summary": _root_cause_excerpt(summary),
                    "last_full_ts": now,
                    "first_seen": (prior or {}).get("first_seen", now),
                    "firings": (prior or {}).get("firings", 0) + 1,
                }
                if len(incidents) > 200:  # keep the most recently investigated
                    state["incidents"] = dict(
                        sorted(incidents.items(), key=lambda kv: kv[1]["last_full_ts"])[-200:]
                    )
            except TriageTimeout as exc:  # abandon this incident, keep polling
                log.error("triage timed out channel=%s exec=%s: %s",
                          channel, alert.execution_id, exc)
                slack.post_reply(
                    channel, ts,
                    f":hourglass_flowing_sand: Triage gave up after "
                    f"{_TRIAGE_DEADLINE_S}s — `{alert.execution_id}` needs a human.",
                )
            except Exception as exc:  # surface into the thread, keep polling
                log.exception("triage failed")
                slack.post_reply(channel, ts, f":warning: Triage failed: `{exc}`")
            handled += 1

        processed.add(ts)
        ch_state["processed"] = list(processed)[-500:]  # cap unbounded growth
        ch_state["last_ts"] = ts
        _save_state(state_path, state)

    return handled


def run_once(cfg: Config, slack: SlackClient, runtime: AgentRuntime, agent) -> int:
    """Process new messages in every configured channel once. Returns alerts triaged."""
    state_path = Path(cfg.state_file)
    state = _load_state(state_path)
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
    if not cfg.slack_alert_channels:
        raise SystemExit(
            "SLACK_ALERT_CHANNEL is required (channel id to poll; comma-separate for several)."
        )
    interval = interval or cfg.poll_interval
    slack = SlackClient(cfg.slack_bot_token)

    with AgentRuntime(server_url=cfg.agentspan_server_url) as runtime:
        agent = build_agent(cfg.model)
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
