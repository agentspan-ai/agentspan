"""Constants and settings."""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = SCRIPT_DIR.parent / "examples"

# ── Example subdirectories ───────────────────────────────────────────────

SUBDIRS = {
    "openai": "agents",  # import name to check dep
    "adk": "google.adk",
    "langgraph": "langgraph",
    "langchain": "langchain",
    "orkes_ocg": "httpx",  # OCG client uses httpx; always available
}

# ── Settings ─────────────────────────────────────────────────────────────


@dataclass
class Settings:
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Judge
    judge_model: str = "gpt-4o-mini"
    judge_max_output_chars: int = 3000
    judge_max_tokens: int = 300
    judge_max_calls: int = 0  # 0 = unlimited
    judge_rate_limit: float = 0.5

    def with_env_overrides(self, env: dict[str, str]) -> "Settings":
        """Return a copy with values from env dict applied."""
        if key := env.get("OPENAI_API_KEY"):
            return dataclasses.replace(self, openai_api_key=key)
        return self

    @classmethod
    def from_env(cls) -> Settings:
        """Create Settings by reading env vars."""
        return cls(
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
            judge_model=os.environ.get("JUDGE_LLM_MODEL", "gpt-4o-mini"),
            judge_max_output_chars=int(os.environ.get("JUDGE_MAX_OUTPUT_CHARS", "3000")),
            judge_max_tokens=int(os.environ.get("JUDGE_MAX_TOKENS", "300")),
            judge_max_calls=int(os.environ.get("JUDGE_MAX_CALLS", "0")),
            judge_rate_limit=float(os.environ.get("JUDGE_RATE_LIMIT", "0.5")),
        )
