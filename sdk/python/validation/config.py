"""Constants, model configs, CSV schemas, and settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ._env import find_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = SCRIPT_DIR.parent / "examples"

# ── Model configs ────────────────────────────────────────────────────────

MODELS = {
    "openai": "openai/gpt-4o",
    "anthropic": "anthropic/claude-sonnet-4-20250514",
    "adk": "google_gemini/gemini-2.0-flash",
}

MODEL_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "adk": "GOOGLE_API_KEY",
}

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


def build_csv_columns(
    models: dict[str, str],
    judge: bool = False,
    baseline_model: str | None = None,
) -> list[str]:
    """Build CSV columns for a dynamic set of models."""
    cols = _PER_PROVIDER_COLS[:]
    if judge:
        cols += ["judge_score", "judge_reason"]
    result = ["example"]
    for p in models:
        result += [f"{p}_{c}" for c in cols]
        if judge and baseline_model and p != baseline_model:
            result += [f"{p}_baseline_score", f"{p}_baseline_reason"]
    result += ["match", "confidence", "notes"]
    return result


# ── Settings ─────────────────────────────────────────────────────────────


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API keys (for model availability detection)
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")

    # Judge
    judge_model: str = Field(default="gpt-4o-mini", validation_alias="JUDGE_LLM_MODEL")
    judge_max_output_chars: int = Field(default=3000, validation_alias="JUDGE_MAX_OUTPUT_CHARS")
    max_judge_calls: int = Field(default=0, validation_alias="MAX_JUDGE_CALLS")  # 0 = unlimited
    judge_rate_limit: float = Field(default=0.5, validation_alias="JUDGE_RATE_LIMIT")
    baseline_model: str = Field(default="openai", validation_alias="BASELINE_MODEL")

    def get_active_models(self) -> dict[str, str]:
        """Return subset of MODELS where the required API key is set."""
        key_map = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "adk": self.google_api_key,
        }
        active = {}
        for name, model_id in MODELS.items():
            key_val = key_map.get(name, "")
            if key_val:
                active[name] = model_id
            else:
                env_var = MODEL_API_KEYS.get(name, "")
                print(f"  Skipping {name}: {env_var} not set")
        return active
