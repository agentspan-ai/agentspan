"""Constants, model configs, CSV schemas, and settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SCRIPT_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = SCRIPT_DIR.parent / "examples"

# ── Model configs ────────────────────────────────────────────────────────

MODELS = {
    "openai": "openai/gpt-4o",
    "anthropic": "anthropic/claude-sonnet-4-20250514",
    "adk": "google_gemini/gemini-2.0-flash",
}

SUBDIRS = {
    "openai": "agents",  # import name to check dep
    "adk": "google.adk",
}

# ── CSV schemas ──────────────────────────────────────────────────────────

_PER_PROVIDER_COLS = [
    "exit_code",
    "status",
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

EXECUTION_CSV_COLUMNS = (
    ["example"]
    + [f"{p}_{c}" for p in MODELS for c in _PER_PROVIDER_COLS]
    + ["match", "confidence", "notes"]
)

JUDGE_CSV_COLUMNS = (
    ["example"]
    + [f"{p}_{c}" for p in MODELS for c in _PER_PROVIDER_COLS + ["judge_score", "judge_reason"]]
    + ["match", "confidence", "notes"]
)

# ── Helpers ───────────────────────────────────────────────────────────────


def _parse_csv(val: str) -> set[str]:
    if not val.strip():
        return set()
    return {s.strip() for s in val.split(",") if s.strip()}


def _parse_kv(val: str) -> dict[str, str]:
    """Parse 'key=val,key=val' into dict."""
    if not val.strip():
        return {}
    result = {}
    for pair in val.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            result[k.strip()] = v.strip()
    return result


# ── Settings (.env for groups/validation, .env.judge for judge secrets) ──

_ENV_FILE = SCRIPT_DIR / ".env"
_JUDGE_ENV_FILE = SCRIPT_DIR / ".env.judge"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), str(_JUDGE_ENV_FILE)),
        env_file_encoding="utf-8",
        extra="allow",
    )

    # Validation
    hitl_stdin: str = Field(default="", validation_alias="HITL_STDIN")

    # Judge
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    judge_model: str = Field(default="gpt-4o-mini", validation_alias="JUDGE_MODEL")

    def get_hitl_stdin(self) -> dict[str, str]:
        return _parse_kv(self.hitl_stdin)

    def get_group(self, name: str) -> set[str]:
        """Read any env var as a CSV set of example stems."""
        val = getattr(self, name.lower(), "") or ""
        return _parse_csv(val)


# Backwards-compat aliases
ValidationSettings = Settings
JudgeSettings = Settings
