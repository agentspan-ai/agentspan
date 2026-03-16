"""Data models for validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Example:
    name: str  # "openai/01_basic_agent" or "01_basic_agent"
    path: Path  # absolute path to .py
    cwd: Path  # working directory for subprocess


_CSV_EXCLUDE = {"stdout", "stderr", "output_text"}


@dataclass
class RunResult:
    exit_code: int = -1
    status: str = "ERROR"
    duration_s: float = 0.0
    workflow_id: str = ""
    tool_calls: int = 0
    tokens_total: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    output_text: str = ""
    output_length: int = 0
    has_error: bool = False
    error_summary: str = ""
    stdout: str = ""
    stderr: str = ""

    def to_csv_dict(self, prefix: str) -> dict[str, object]:
        return {f"{prefix}_{k}": v for k, v in asdict(self).items() if k not in _CSV_EXCLUDE}


@dataclass
class ExampleResult:
    example: Example = None  # type: ignore[assignment]
    results: dict[str, RunResult] = field(default_factory=dict)
    match: str = ""
    confidence: str = ""
    notes: str = ""
