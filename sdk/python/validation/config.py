"""Constants, CSV schemas, and settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = SCRIPT_DIR.parent / "examples"

# ── Example subdirectories ───────────────────────────────────────────────

SUBDIRS = {
    "openai": "agents",  # import name to check dep
    "adk": "google.adk",
}

# ── Pricing (per 1K tokens) ─────────────────────────────────────────────

MODEL_PRICING = {
    "openai": {"prompt": 0.0025, "completion": 0.01},
    "anthropic": {"prompt": 0.003, "completion": 0.015},
    "adk": {"prompt": 0.0001, "completion": 0.0004},
}

# ── CSV schema ───────────────────────────────────────────────────────────

SINGLE_RUN_CSV_COLUMNS = [
    "example",
    "status",
    "exit_code",
    "duration_s",
    "workflow_id",
    "tool_calls",
    "tokens_total",
    "tokens_prompt",
    "tokens_completion",
    "output_length",
    "has_error",
    "error_summary",
]

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
