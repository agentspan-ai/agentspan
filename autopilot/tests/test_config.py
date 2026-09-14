"""Tests for AutopilotConfig."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from autopilot.config import AutopilotConfig


class TestDefaults:
    def test_default_server_url(self):
        cfg = AutopilotConfig()
        assert cfg.server_url == "http://localhost:6767"

    def test_default_llm_model(self):
        cfg = AutopilotConfig()
        assert cfg.llm_model == "openai/gpt-4o-mini"

    def test_default_base_dir_is_home_based(self):
        cfg = AutopilotConfig()
        assert cfg.base_dir == Path.home() / ".agentspan" / "autopilot"

    def test_default_last_seen_empty(self):
        cfg = AutopilotConfig()
        assert cfg.last_seen == {}


class TestFromFile:
    def test_loads_from_yaml(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "server_url": "http://custom:9999",
            "llm_model": "anthropic/claude-sonnet-4-20250514",
        }))

        cfg = AutopilotConfig.from_file(config_file)

        assert cfg.server_url == "http://custom:9999"
        assert cfg.llm_model == "anthropic/claude-sonnet-4-20250514"

    def test_missing_file_returns_defaults(self, tmp_path: Path):
        cfg = AutopilotConfig.from_file(tmp_path / "nonexistent.yaml")

        assert cfg.server_url == "http://localhost:6767"
        assert cfg.llm_model == "openai/gpt-4o-mini"

    def test_partial_yaml_uses_defaults_for_missing(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"server_url": "http://partial:1234"}))

        cfg = AutopilotConfig.from_file(config_file)

        assert cfg.server_url == "http://partial:1234"
        assert cfg.llm_model == "openai/gpt-4o-mini"

    def test_loads_last_seen(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "last_seen": {"agent_a": "2026-01-01T00:00:00"}
        }))

        cfg = AutopilotConfig.from_file(config_file)
        assert cfg.last_seen == {"agent_a": "2026-01-01T00:00:00"}


class TestSaveAndReload:
    def test_save_creates_file(self, tmp_path: Path):
        cfg = AutopilotConfig(
            server_url="http://saved:5555",
            llm_model="google/gemini-pro",
            base_dir=tmp_path,
        )
        cfg.save()

        reloaded = AutopilotConfig.from_file(tmp_path / "config.yaml")
        assert reloaded.server_url == "http://saved:5555"
        assert reloaded.llm_model == "google/gemini-pro"

    def test_save_preserves_last_seen(self, tmp_path: Path):
        cfg = AutopilotConfig(
            base_dir=tmp_path,
            last_seen={"bot": "2026-04-12T10:00:00"},
        )
        cfg.save()

        reloaded = AutopilotConfig.from_file(tmp_path / "config.yaml")
        assert reloaded.last_seen == {"bot": "2026-04-12T10:00:00"}


class TestEnvOverride:
    def test_env_overrides_server_url(self, monkeypatch, tmp_path: Path):
        # Prevent reading real filesystem config
        monkeypatch.setenv("AUTOPILOT_BASE_DIR", str(tmp_path))
        monkeypatch.setenv("AGENTSPAN_SERVER_URL", "http://env:8888")

        cfg = AutopilotConfig.from_env()
        assert cfg.server_url == "http://env:8888"

    def test_env_overrides_llm_model(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("AUTOPILOT_BASE_DIR", str(tmp_path))
        monkeypatch.setenv("AGENTSPAN_LLM_MODEL", "anthropic/claude-opus-4-20250514")

        cfg = AutopilotConfig.from_env()
        assert cfg.llm_model == "anthropic/claude-opus-4-20250514"

    def test_env_without_vars_uses_file_defaults(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("AUTOPILOT_BASE_DIR", str(tmp_path))
        monkeypatch.delenv("AGENTSPAN_SERVER_URL", raising=False)
        monkeypatch.delenv("AGENTSPAN_LLM_MODEL", raising=False)

        cfg = AutopilotConfig.from_env()
        assert cfg.server_url == "http://localhost:6767"


class TestDirectoryProperties:
    def test_autopilot_dir(self, tmp_path: Path):
        cfg = AutopilotConfig(base_dir=tmp_path)
        assert cfg.autopilot_dir == tmp_path

    def test_agents_dir(self, tmp_path: Path):
        cfg = AutopilotConfig(base_dir=tmp_path)
        assert cfg.agents_dir == tmp_path / "agents"

    def test_orchestrator_dir(self, tmp_path: Path):
        cfg = AutopilotConfig(base_dir=tmp_path)
        assert cfg.orchestrator_dir == tmp_path / "orchestrator"


class TestLastSeen:
    def test_update_last_seen(self):
        cfg = AutopilotConfig()
        cfg.last_seen["my_agent"] = "2026-04-12T12:00:00"
        assert cfg.last_seen["my_agent"] == "2026-04-12T12:00:00"

    def test_last_seen_roundtrip(self, tmp_path: Path):
        cfg = AutopilotConfig(
            base_dir=tmp_path,
            last_seen={"a": "t1", "b": "t2"},
        )
        cfg.save()

        reloaded = AutopilotConfig.from_file(tmp_path / "config.yaml")
        assert reloaded.last_seen == {"a": "t1", "b": "t2"}
