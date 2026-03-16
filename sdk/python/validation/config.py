"""Constants, model configs, CSV schemas, and settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ._env import load_env

load_env()

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


@dataclass
class Settings:
    # API keys (for model availability detection)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Judge
    judge_model: str = "gpt-4o-mini"
    judge_max_output_chars: int = 3000
    max_judge_calls: int = 0  # 0 = unlimited
    judge_rate_limit: float = 0.5
    baseline_model: str = "openai"

    @classmethod
    def from_env(cls) -> Settings:
        """Create Settings by reading env vars (dotenv loaded at module level)."""
        return cls(
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
            judge_model=os.environ.get("JUDGE_LLM_MODEL", "gpt-4o-mini"),
            judge_max_output_chars=int(os.environ.get("JUDGE_MAX_OUTPUT_CHARS", "3000")),
            max_judge_calls=int(os.environ.get("MAX_JUDGE_CALLS", "0")),
            judge_rate_limit=float(os.environ.get("JUDGE_RATE_LIMIT", "0.5")),
            baseline_model=os.environ.get("BASELINE_MODEL", "openai"),
        )

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
