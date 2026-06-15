"""Slack Socket Mode listener: alert in channel -> triage -> threaded reply."""
from __future__ import annotations

import logging

from agentspan.agents import AgentRuntime
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from .agent import build_agent
from .alert import Alert, parse_alert
from .config import Config

log = logging.getLogger("oncall_agent")


def _triage_prompt(alert: Alert) -> str:
    return (
        "A cluster health-check alert fired.\n\n"
        f"Alert text:\n{alert.raw}\n\n"
        f"The failing health_check execution id is: {alert.execution_id}\n"
        "Investigate (read-only) and produce the triage summary."
    )


def build_slack_app(cfg: Config, runtime: AgentRuntime) -> App:
    app = App(token=cfg.slack_bot_token)
    agent = build_agent(cfg.model)

    @app.event("message")
    def handle_message(event, say):
        # Ignore bot posts, edits, joins, and other subtypes.
        if event.get("bot_id") or event.get("subtype"):
            return
        if cfg.slack_alert_channel and event.get("channel") != cfg.slack_alert_channel:
            return

        alert = parse_alert(event.get("text", ""))
        if not alert:
            return

        thread_ts = event.get("thread_ts") or event.get("ts")
        log.info(
            "triage start exec=%s cluster=%s sev=%s",
            alert.execution_id,
            alert.cluster,
            alert.severity,
        )
        say(
            text=f":mag: On-call triage starting for execution `{alert.execution_id}`…",
            thread_ts=thread_ts,
        )
        try:
            result = runtime.run(agent, _triage_prompt(alert))
            summary = getattr(result, "output", None) or str(result)
        except Exception as exc:  # surface failures into the thread, don't crash the listener
            log.exception("triage failed")
            say(text=f":warning: Triage failed: `{exc}`", thread_ts=thread_ts)
            return

        header = (
            "*:robot_face: On-call triage (dry-run · read-only)*\n"
            if cfg.dry_run
            else "*:robot_face: On-call triage*\n"
        )
        say(text=header + summary, thread_ts=thread_ts)

    return app


def run(cfg: Config | None = None) -> None:
    cfg = cfg or Config.from_env()
    logging.basicConfig(level=logging.INFO)
    with AgentRuntime(server_url=cfg.agentspan_server_url) as runtime:
        app = build_slack_app(cfg, runtime)
        handler = SocketModeHandler(app, cfg.slack_app_token)
        log.info("on-call agent listening (dry_run=%s, model=%s)", cfg.dry_run, cfg.model)
        handler.start()
