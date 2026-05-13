# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""SharedStore — file-backed key-value state for subagent coordination.

The single-process ``session_store`` only sees one harness's state. A
parent and a subagent (which may run in its own ``HarnessRuntime``) need
to exchange structured artifacts: the tech-lead writes architecture
notes, the coder reads them. The contextbook in ``100_issue_fixer_agent``
solves this by writing markdown files; the harness equivalent is a
JSON-on-disk kv store keyed by section.

Concurrent writers serialize via a per-key lockfile. Reads are
copy-on-load — callers get a snapshot, not a live reference.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agentspan.harness.shared_store")


class SharedStore:
    """File-backed kv store under ``<dir>/sections/<key>.json``.

    Use one ``SharedStore`` per logical session — pass the same root
    directory to the parent and to subagents to give them a shared view.
    """

    def __init__(self, root: str) -> None:
        self._root = os.path.abspath(root)
        os.makedirs(self._root, exist_ok=True)
        self._sections_dir = os.path.join(self._root, "sections")
        os.makedirs(self._sections_dir, exist_ok=True)

    @property
    def root(self) -> str:
        return self._root

    def path_for(self, key: str) -> str:
        safe = _safe_key(key)
        return os.path.join(self._sections_dir, safe + ".json")

    def write(self, key: str, value: Any) -> str:
        """Atomically replace the value at ``key`` and return the file path.

        ``value`` must be JSON-serializable. The on-disk record is wrapped
        with a timestamp so callers can age out stale entries.
        """
        path = self.path_for(key)
        record = {"ts": time.time(), "key": key, "value": value}
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._sections_dir, prefix=".write_", suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fp:
                json.dump(record, fp, default=str)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return path

    def read(self, key: str) -> Optional[Any]:
        path = self.path_for(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fp:
                record = json.load(fp)
            return record.get("value")
        except (OSError, json.JSONDecodeError):
            logger.exception("shared_store read failed for %s", key)
            return None

    def list(self) -> List[str]:
        try:
            return sorted(
                os.path.splitext(f)[0]
                for f in os.listdir(self._sections_dir)
                if f.endswith(".json")
            )
        except OSError:
            return []

    def delete(self, key: str) -> bool:
        path = self.path_for(key)
        try:
            os.unlink(path)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False


def _safe_key(key: str) -> str:
    """Limit key to a filesystem-safe charset; reject path traversal."""
    out = []
    for ch in key:
        if ch.isalnum() or ch in "-_.":
            out.append(ch)
        else:
            out.append("_")
    name = "".join(out).strip("._") or "key"
    return name[:128]
