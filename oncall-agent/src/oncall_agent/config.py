"""Environment-driven configuration for the on-call agent."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv() -> None:
    """Best-effort load of a local .env, if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass


@dataclass
class Config:
    # ah5r-prod Conductor API (the agent runs inside ah5r-prod and dispatches
    # agent-handler workflows here).
    conductor_server_url: str
    conductor_key_id: str
    conductor_key_secret: str

    # Slack (Socket Mode): bot token (xoxb-) + app-level token (xapp-).
    slack_bot_token: str
    slack_app_token: str
    slack_alert_channel: str | None  # restrict to one channel id, or None for any

    # Agentspan server that runs the agent loop / LLM calls.
    agentspan_server_url: str
    model: str

    # When true (default), output is clearly labelled advisory. The agent is
    # read-only regardless; this only affects messaging.
    dry_run: bool

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv()
        return cls(
            conductor_server_url=os.environ.get(
                "CONDUCTOR_SERVER_URL", "https://ah5r-prod.orkesconductor.com/api"
            ),
            conductor_key_id=os.environ.get("CONDUCTOR_AUTH_KEY", ""),
            conductor_key_secret=os.environ.get("CONDUCTOR_AUTH_SECRET", ""),
            slack_bot_token=os.environ.get("SLACK_BOT_TOKEN", ""),
            slack_app_token=os.environ.get("SLACK_APP_TOKEN", ""),
            slack_alert_channel=os.environ.get("SLACK_ALERT_CHANNEL") or None,
            agentspan_server_url=os.environ.get(
                "AGENTSPAN_SERVER_URL", "http://localhost:6767/api"
            ),
            model=os.environ.get("ONCALL_MODEL", "anthropic/claude-sonnet-4-6"),
            dry_run=os.environ.get("ONCALL_DRY_RUN", "true").lower() != "false",
        )
