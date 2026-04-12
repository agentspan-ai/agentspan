"""AutopilotConfig — loads from ~/.agentspan/autopilot/config.yaml with env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _default_base_dir() -> Path:
    return Path.home() / ".agentspan" / "autopilot"


@dataclass
class AutopilotConfig:
    """Configuration for the Agentspan Autopilot runtime.

    Loads from ``~/.agentspan/autopilot/config.yaml`` and supports
    environment variable overrides for server_url and llm_model.

    Attributes:
        server_url: URL of the Agentspan server.
        llm_model: Default LLM model in ``"provider/model"`` format.
        base_dir: Root directory for autopilot configuration files.
        last_seen: Per-agent timestamps for notification tracking.
    """

    server_url: str = "http://localhost:6767"
    llm_model: str = "openai/gpt-4o-mini"
    base_dir: Path = field(default_factory=_default_base_dir)
    last_seen: Dict[str, str] = field(default_factory=dict)

    # -- Directory properties --------------------------------------------------

    @property
    def autopilot_dir(self) -> Path:
        """Root autopilot configuration directory."""
        return self.base_dir

    @property
    def agents_dir(self) -> Path:
        """Directory containing agent definitions."""
        return self.base_dir / "agents"

    @property
    def orchestrator_dir(self) -> Path:
        """Directory containing orchestrator configurations."""
        return self.base_dir / "orchestrator"

    # -- Persistence -----------------------------------------------------------

    @classmethod
    def from_file(cls, path: Optional[Path] = None) -> "AutopilotConfig":
        """Load config from a YAML file.

        Args:
            path: Path to the YAML config file.  Defaults to
                ``~/.agentspan/autopilot/config.yaml``.

        Returns:
            An ``AutopilotConfig`` populated from the file (missing keys
            use defaults).  If the file does not exist, returns defaults.
        """
        if path is None:
            path = _default_base_dir() / "config.yaml"

        if not path.exists():
            return cls()

        try:
            with open(path) as f:
                raw: Dict[str, Any] = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            # Corrupted or unreadable config — use defaults
            return cls()

        base_dir = Path(raw["base_dir"]) if "base_dir" in raw else _default_base_dir()
        last_seen = raw.get("last_seen", {})
        if not isinstance(last_seen, dict):
            last_seen = {}

        return cls(
            server_url=raw.get("server_url", cls.server_url),
            llm_model=raw.get("llm_model", cls.llm_model),
            base_dir=base_dir,
            last_seen=last_seen,
        )

    @classmethod
    def from_env(cls) -> "AutopilotConfig":
        """Build config from environment variables, falling back to file defaults.

        Recognised variables:
            ``AGENTSPAN_SERVER_URL`` — overrides ``server_url``
            ``AGENTSPAN_LLM_MODEL`` — overrides ``llm_model``
        """
        cfg = cls.from_file()
        if url := os.environ.get("AGENTSPAN_SERVER_URL"):
            cfg.server_url = url
        if model := os.environ.get("AGENTSPAN_LLM_MODEL"):
            cfg.llm_model = model
        return cfg

    def save(self, path: Optional[Path] = None) -> None:
        """Persist the config to a YAML file.

        Args:
            path: Destination path.  Defaults to
                ``<base_dir>/config.yaml``.
        """
        if path is None:
            path = self.base_dir / "config.yaml"

        path.parent.mkdir(parents=True, exist_ok=True)

        data: Dict[str, Any] = {
            "server_url": self.server_url,
            "llm_model": self.llm_model,
            "base_dir": str(self.base_dir),
        }
        if self.last_seen:
            data["last_seen"] = self.last_seen

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
