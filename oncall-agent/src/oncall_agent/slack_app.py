"""Slack polling: read the alert channel, triage each new alert, reply in-thread.

Mirrors the repo's Slack convention (sdk/python/examples/91_slack_autofix_agent.py):
plain Web API calls with a bot token (no Socket Mode), run-once or ``--loop``, and
dedup via a local state file. Slack I/O lives here — the triage agent stays pure and
only investigates a given execution id.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests
from conductor.ai.agents import AgentRuntime

from .agent import build_agent
from .alert import Alert, parse_alert
from .config import Config
from .runtime_compat import summary_text

log = logging.getLogger("oncall_agent")
_SLACK_API = "https://slack.com/api"
_POLL_LIMIT = 20


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


def _triage_prompt(alert: Alert) -> str:
    return (
        "A cluster health-check alert fired.\n\n"
        f"Alert text:\n{alert.raw}\n\n"
        f"The failing health_check execution id is: {alert.execution_id}\n"
        "Investigate (read-only) and produce the triage summary."
    )


def _header(cfg: Config) -> str:
    return (
        "*:robot_face: On-call triage (dry-run · read-only)*\n"
        if cfg.dry_run
        else "*:robot_face: On-call triage*\n"
    )


def run_once(cfg: Config, slack: SlackClient, runtime: AgentRuntime, agent) -> int:
    """Process new messages once. Returns the number of alerts triaged."""
    state_path = Path(cfg.state_file)
    state = _load_state(state_path)
    processed = set(state.get("processed") or [])

    # Slack returns newest-first; process oldest-first so the window advances cleanly.
    messages = slack.read_messages(
        cfg.slack_alert_channel, oldest=state.get("last_ts") or "0", limit=_POLL_LIMIT
    )
    messages.sort(key=lambda m: float(m["ts"]))

    handled = 0
    for msg in messages:
        ts = msg["ts"]
        if ts in processed:
            continue
        alert = parse_alert(msg.get("text", ""))
        if alert:
            log.info("triage exec=%s cluster=%s sev=%s", alert.execution_id, alert.cluster, alert.severity)
            slack.post_reply(
                cfg.slack_alert_channel,
                ts,
                f":mag: On-call triage starting for execution `{alert.execution_id}`…",
            )
            try:
                result = runtime.run(agent, _triage_prompt(alert))
                summary = summary_text(result)
                slack.post_reply(cfg.slack_alert_channel, ts, _header(cfg) + summary)
            except Exception as exc:  # surface into the thread, keep polling
                log.exception("triage failed")
                slack.post_reply(cfg.slack_alert_channel, ts, f":warning: Triage failed: `{exc}`")
            handled += 1

        processed.add(ts)
        state["processed"] = list(processed)[-500:]  # cap unbounded growth
        state["last_ts"] = ts
        _save_state(state_path, state)

    return handled


def run(cfg: Config | None = None, loop: bool = False, interval: int | None = None) -> None:
    cfg = cfg or Config.from_env()
    logging.basicConfig(level=logging.INFO)
    from .runtime_compat import use_thread_workers_if_needed

    use_thread_workers_if_needed()
    if not cfg.slack_alert_channel:
        raise SystemExit("SLACK_ALERT_CHANNEL is required (the channel id to poll).")
    interval = interval or cfg.poll_interval
    slack = SlackClient(cfg.slack_bot_token)

    with AgentRuntime(server_url=cfg.agentspan_server_url) as runtime:
        agent = build_agent(cfg.model)
        log.info(
            "on-call agent polling channel=%s (loop=%s, interval=%ss, dry_run=%s, model=%s)",
            cfg.slack_alert_channel, loop, interval, cfg.dry_run, cfg.model,
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
