"""Data models for validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Example:
    name: str  # "openai/01_basic_agent" or "01_basic_agent"
    path: Path  # absolute path to .py
    cwd: Path  # working directory for subprocess


@dataclass
class RunResult:
    exit_code: int = -1
    status: str = "ERROR"
    duration_s: float = 0.0
    execution_id: str = ""
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


@dataclass
class SingleResult:
    """Result of running one example with one model (single-run mode)."""

    example: Example = None  # type: ignore[assignment]
    result: RunResult = None  # type: ignore[assignment]
