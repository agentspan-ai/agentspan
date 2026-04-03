"""TOML configuration for multi-run validation."""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class RunConfig:
    name: str = ""
    group: str | None = None
    model: str = "openai/gpt-4o"
    secondary_model: str | None = None
    native: bool = False
    parallel: bool = True
    max_workers: int = 8
    timeout: int = 300
    retries: int = 0
    server_url: str = "http://localhost:6767/api"
    env: dict = field(default_factory=dict)


@dataclass
class JudgeConfig:
    baseline_run: str | None = None
    model: str = "gpt-4o-mini"
    max_output_chars: int = 3000
    max_tokens: int = 300
    rate_limit: float = 0.5
    max_calls: int = 0
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class DisplayConfig:
    max_example_rows: int = 40


@dataclass
class MultiRunConfig:
    runs: dict[str, RunConfig] = field(default_factory=dict)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    env: dict = field(default_factory=dict)


_RUN_FIELDS = {f.name for f in RunConfig.__dataclass_fields__.values()}
_JUDGE_FIELDS = {f.name for f in JudgeConfig.__dataclass_fields__.values()}
_DISPLAY_FIELDS = {f.name for f in DisplayConfig.__dataclass_fields__.values()}


def load_toml_config(path: Path) -> MultiRunConfig:
    """Load and validate a TOML multi-run config file."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    defaults = raw.get("defaults", {})
    judge_raw = raw.get("judge", {})
    runs_raw = raw.get("runs", {})
    display_raw = raw.get("display", {})
    global_env = raw.get("env", {})

    # Warn on unknown top-level keys
    known_top = {"defaults", "judge", "runs", "display", "env"}
    for k in raw:
        if k not in known_top:
            warnings.warn(f"Unknown top-level key in config: '{k}'")

    # Warn on unknown defaults keys
    for k in defaults:
        if k not in _RUN_FIELDS:
            warnings.warn(f"Unknown key in [defaults]: '{k}'")

    # Warn on unknown judge keys
    for k in judge_raw:
        if k not in _JUDGE_FIELDS and k != "env":
            warnings.warn(f"Unknown key in [judge]: '{k}'")

    # Warn on unknown display keys
    for k in display_raw:
        if k not in _DISPLAY_FIELDS:
            warnings.warn(f"Unknown key in [display]: '{k}'")

    # Build JudgeConfig + DisplayConfig
    judge = JudgeConfig(**{k: v for k, v in judge_raw.items() if k in _JUDGE_FIELDS})
    judge.env = judge_raw.get("env", {})
    display = DisplayConfig(**{k: v for k, v in display_raw.items() if k in _DISPLAY_FIELDS})

    # Build RunConfigs — merge defaults into each run
    if not runs_raw:
        print("ERROR: Config must define at least one [runs.*] section.", file=sys.stderr)
        sys.exit(1)

    runs: dict[str, RunConfig] = {}
    for run_name, run_raw in runs_raw.items():
        # Warn on unknown run keys (env is a nested dict, not a scalar field)
        for k in run_raw:
            if k not in _RUN_FIELDS:
                warnings.warn(f"Unknown key in [runs.{run_name}]: '{k}'")

        run_env = run_raw.get("env", {})
        merged = {**defaults, **run_raw}
        merged["name"] = run_name
        rc = RunConfig(**{k: v for k, v in merged.items() if k in _RUN_FIELDS})
        rc.env = run_env
        runs[run_name] = rc

    config = MultiRunConfig(runs=runs, judge=judge, display=display, env=global_env)

    # Validate baseline_run
    if judge.baseline_run and judge.baseline_run not in runs:
        available = ", ".join(runs.keys())
        print(
            f"ERROR: judge.baseline_run '{judge.baseline_run}' not in runs. Available: {available}",
            file=sys.stderr,
        )
        sys.exit(1)

    return config


def resolve_runs(config: MultiRunConfig, selected: list[str] | None) -> list[RunConfig]:
    """Filter runs by names. Error if any name is unknown."""
    if not selected:
        return list(config.runs.values())

    unknown = [n for n in selected if n not in config.runs]
    if unknown:
        available = ", ".join(config.runs.keys())
        print(
            f"ERROR: Unknown run(s): {', '.join(unknown)}. Available: {available}",
            file=sys.stderr,
        )
        sys.exit(1)

    return [config.runs[n] for n in selected]
