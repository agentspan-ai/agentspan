# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for the server-instance + env-hash gate on _sync_provider_env_to_server.

Marker schema is::

    {
      "<server_url>": {"instance_id": "<uuid>", "env_hash": "<sha256>"}
    }

Sync runs iff EITHER the instance_id is new (server JVM restarted) OR the
env_hash has changed (user fixed a shell-config typo and re-ran without
restarting the server). This closes a regression from the original
"gate by instance_id only" design that re-introduced the cached-bad-key bug.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def _make_runtime(server_url: str = "http://localhost:6767/api"):
    """Construct an AgentRuntime against localhost with heavy I/O mocked out."""
    with (
        patch("conductor.client.orkes_clients.OrkesClients"),
        patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True),
        patch("agentspan.agents.runtime.server.ensure_server_running"),
        patch("agentspan.agents.runtime.server._is_server_ready", return_value=True),
    ):
        from agentspan.agents.runtime.config import AgentConfig
        from agentspan.agents.runtime.runtime import AgentRuntime

        config = AgentConfig(
            server_url=server_url,
            auto_start_workers=False,
            auto_start_server=False,
        )
        return AgentRuntime(config=config)


def _mock_info_response(instance_id: str):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"instance_id": instance_id}
    resp.raise_for_status.return_value = None
    return resp


def _put_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    return resp


def _current_env_hash() -> str:
    """Same hash the runtime computes — used to build matching markers in tests."""
    from agentspan.agents.runtime.runtime import _compute_env_hash

    return _compute_env_hash()


class TestFingerprintGate:
    """Marker stops repeated syncs from clobbering the server for the same JVM
    + same env, and re-runs sync when either changes."""

    def test_skips_sync_when_both_instance_and_env_match(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        marker = tmp_path / "sync-marker.json"
        monkeypatch.setattr(
            "agentspan.agents.runtime.runtime._sync_marker_path", lambda: marker
        )
        marker.write_text(
            json.dumps(
                {
                    "http://localhost:6767/api": {
                        "instance_id": "instance-A",
                        "env_hash": _current_env_hash(),
                    }
                }
            )
        )

        with patch("httpx.get", return_value=_mock_info_response("instance-A")) as g, patch(
            "httpx.put", return_value=_put_response()
        ) as p:
            _make_runtime()

        assert g.called  # info probed
        assert not p.called  # no credential PUT

    def test_syncs_when_instance_id_changes(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        marker = tmp_path / "sync-marker.json"
        monkeypatch.setattr(
            "agentspan.agents.runtime.runtime._sync_marker_path", lambda: marker
        )
        marker.write_text(
            json.dumps(
                {
                    "http://localhost:6767/api": {
                        "instance_id": "instance-OLD",
                        "env_hash": _current_env_hash(),  # env unchanged
                    }
                }
            )
        )

        with patch("httpx.get", return_value=_mock_info_response("instance-NEW")), patch(
            "httpx.put", return_value=_put_response()
        ) as p:
            _make_runtime()

        assert p.called
        updated = json.loads(marker.read_text())["http://localhost:6767/api"]
        assert updated["instance_id"] == "instance-NEW"

    def test_syncs_when_env_hash_changes_even_if_instance_same(self, monkeypatch, tmp_path):
        # THE BUG THIS GUARDS AGAINST: user fixed a typo'd API key and re-ran
        # without restarting the server. instance_id stays the same; env_hash
        # changes; we MUST re-sync so the corrected key reaches the store.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-CORRECTED")
        marker = tmp_path / "sync-marker.json"
        monkeypatch.setattr(
            "agentspan.agents.runtime.runtime._sync_marker_path", lambda: marker
        )
        # Marker reflects the previous (typo'd) env hash.
        marker.write_text(
            json.dumps(
                {
                    "http://localhost:6767/api": {
                        "instance_id": "instance-A",
                        "env_hash": "stale-typo-hash",
                    }
                }
            )
        )

        with patch("httpx.get", return_value=_mock_info_response("instance-A")), patch(
            "httpx.put", return_value=_put_response()
        ) as p:
            _make_runtime()

        assert p.called  # sync ran despite same instance_id
        # Marker was updated with the new env_hash.
        updated = json.loads(marker.read_text())["http://localhost:6767/api"]
        assert updated["env_hash"] == _current_env_hash()
        assert updated["env_hash"] != "stale-typo-hash"

    def test_syncs_when_marker_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        marker = tmp_path / "sync-marker.json"  # not created
        monkeypatch.setattr(
            "agentspan.agents.runtime.runtime._sync_marker_path", lambda: marker
        )

        with patch("httpx.get", return_value=_mock_info_response("instance-A")), patch(
            "httpx.put", return_value=_put_response()
        ) as p:
            _make_runtime()

        assert p.called
        assert marker.exists()
        entry = json.loads(marker.read_text())["http://localhost:6767/api"]
        assert entry["instance_id"] == "instance-A"
        assert entry["env_hash"] == _current_env_hash()

    def test_syncs_when_marker_corrupt(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        marker = tmp_path / "sync-marker.json"
        marker.write_text("{not-valid-json")
        monkeypatch.setattr(
            "agentspan.agents.runtime.runtime._sync_marker_path", lambda: marker
        )

        with patch("httpx.get", return_value=_mock_info_response("instance-A")), patch(
            "httpx.put", return_value=_put_response()
        ) as p:
            _make_runtime()

        assert p.called
        entry = json.loads(marker.read_text())["http://localhost:6767/api"]
        assert entry["instance_id"] == "instance-A"

    def test_legacy_marker_string_format_triggers_resync(self, monkeypatch, tmp_path):
        # Old marker schema (server_url → instance_id string) must trigger a
        # re-sync, not crash. After sync, the marker is rewritten in the new
        # schema.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        marker = tmp_path / "sync-marker.json"
        marker.write_text(json.dumps({"http://localhost:6767/api": "instance-A"}))
        monkeypatch.setattr(
            "agentspan.agents.runtime.runtime._sync_marker_path", lambda: marker
        )

        with patch("httpx.get", return_value=_mock_info_response("instance-A")), patch(
            "httpx.put", return_value=_put_response()
        ) as p:
            _make_runtime()

        assert p.called
        entry = json.loads(marker.read_text())["http://localhost:6767/api"]
        assert isinstance(entry, dict)
        assert entry["instance_id"] == "instance-A"
        assert entry["env_hash"] == _current_env_hash()

    def test_syncs_when_info_endpoint_unreachable(self, monkeypatch, tmp_path):
        # Old server without /api/info → fall back to unconditional sync.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        marker = tmp_path / "sync-marker.json"
        monkeypatch.setattr(
            "agentspan.agents.runtime.runtime._sync_marker_path", lambda: marker
        )
        marker.write_text(
            json.dumps(
                {
                    "http://localhost:6767/api": {
                        "instance_id": "instance-A",
                        "env_hash": _current_env_hash(),
                    }
                }
            )
        )

        def fake_get(*args, **kwargs):
            raise RuntimeError("connection refused")

        with patch("httpx.get", side_effect=fake_get), patch(
            "httpx.put", return_value=_put_response()
        ) as p:
            _make_runtime()

        assert p.called

    def test_marker_isolated_per_server_url(self, monkeypatch, tmp_path):
        # Two servers on different ports → independent fingerprints.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        marker = tmp_path / "sync-marker.json"
        monkeypatch.setattr(
            "agentspan.agents.runtime.runtime._sync_marker_path", lambda: marker
        )
        marker.write_text(
            json.dumps(
                {
                    "http://localhost:6767/api": {
                        "instance_id": "instance-A",
                        "env_hash": _current_env_hash(),
                    },
                    "http://localhost:7777/api": {
                        "instance_id": "instance-X",
                        "env_hash": _current_env_hash(),
                    },
                }
            )
        )

        with patch("httpx.get", return_value=_mock_info_response("instance-X")), patch(
            "httpx.put", return_value=_put_response()
        ) as p:
            _make_runtime(server_url="http://localhost:7777/api")

        assert not p.called
        # 6767's entry untouched.
        kept = json.loads(marker.read_text())["http://localhost:6767/api"]
        assert kept["instance_id"] == "instance-A"


class TestComputeEnvHash:
    """The env-hash function itself."""

    def test_same_env_produces_same_hash(self, monkeypatch):
        from agentspan.agents.runtime.runtime import _compute_env_hash

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        h1 = _compute_env_hash()
        h2 = _compute_env_hash()
        assert h1 == h2

    def test_different_env_produces_different_hash(self, monkeypatch):
        from agentspan.agents.runtime.runtime import _compute_env_hash

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-old")
        h_old = _compute_env_hash()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-new")
        h_new = _compute_env_hash()
        assert h_old != h_new

    def test_unset_env_var_is_treated_as_empty_string(self, monkeypatch):
        # Removing a var changes the hash — important because going from
        # "ANTHROPIC_API_KEY=bad" to unset is a meaningful change.
        from agentspan.agents.runtime.runtime import _compute_env_hash

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        h_set = _compute_env_hash()
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        h_unset = _compute_env_hash()
        assert h_set != h_unset
