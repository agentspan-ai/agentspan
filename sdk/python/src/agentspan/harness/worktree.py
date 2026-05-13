# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""WorktreeManager — git worktree lifecycle for editing subagents.

Per design §14: editing subagents that may run in parallel get isolated
git worktrees so concurrent edits don't race on the same checkout.

Lifecycle:

  ``create(branch=...)`` → spawn ``git worktree add`` at a new path under
    a managed root, returning the absolute path.
  ``has_changes(path)`` → True iff the worktree has uncommitted edits or
    commits diverging from the base.
  ``cleanup(path, *, force=False)`` → idempotent. By default keeps the
    worktree if there are uncommitted changes or unmerged commits and
    returns False; ``force=True`` discards them.

The manager refuses operations on paths that aren't underneath its
managed root, to prevent accidental cleanup of the user's actual
worktree.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("agentspan.harness.worktree")


@dataclass
class WorktreeInfo:
    path: str
    branch: str
    repo: str  # the original repo's git directory


class WorktreeManager:
    """Create and manage git worktrees for subagents.

    Construction takes the source repo path. The manager creates a
    sibling directory ``./.agentspan-worktrees/`` (or honors
    ``$AGENTSPAN_HARNESS_WORKTREES_DIR``) where it provisions worktrees.
    """

    def __init__(
        self,
        repo_path: str,
        *,
        worktree_root: Optional[str] = None,
    ) -> None:
        self._repo = os.path.abspath(repo_path)
        if worktree_root is None:
            override = os.environ.get("AGENTSPAN_HARNESS_WORKTREES_DIR")
            worktree_root = override or os.path.join(self._repo, ".agentspan-worktrees")
        self._root = os.path.abspath(worktree_root)
        os.makedirs(self._root, exist_ok=True)

    @property
    def repo(self) -> str:
        return self._repo

    @property
    def root(self) -> str:
        return self._root

    # ── Lifecycle ────────────────────────────────────────────────────

    async def create(
        self,
        *,
        branch: Optional[str] = None,
        base: str = "HEAD",
    ) -> WorktreeInfo:
        if not await self._is_git_repo():
            raise RuntimeError(f"{self._repo} is not a git repository")

        if branch is None:
            branch = f"agentspan/wt/{uuid.uuid4().hex[:10]}"

        # Pick a unique path inside the managed root.
        path = os.path.join(self._root, f"wt-{uuid.uuid4().hex[:10]}")
        await self._git("worktree", "add", "-b", branch, path, base)
        return WorktreeInfo(path=path, branch=branch, repo=self._repo)

    async def has_changes(self, path: str) -> bool:
        """True iff the worktree at ``path`` has uncommitted changes or
        commits diverging from the parent ``HEAD``.
        """
        path = os.path.abspath(path)
        if not self._owned(path):
            raise RuntimeError(f"worktree path is not under managed root: {path}")
        # uncommitted? (working tree + index)
        out = await self._git_at(path, "status", "--porcelain")
        if out.strip():
            return True
        # commits ahead of the parent repo's HEAD?
        try:
            base = (await self._git("rev-parse", "HEAD")).strip()
            out = await self._git_at(path, "log", f"{base}..HEAD", "--oneline")
            if out.strip():
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    async def cleanup(self, path: str, *, force: bool = False) -> bool:
        """Remove a worktree. Returns True iff removed.

        If the worktree has uncommitted changes or unmerged commits and
        ``force`` is False, returns False without removing — caller must
        explicitly decide to discard.
        """
        path = os.path.abspath(path)
        if not self._owned(path):
            logger.warning("worktree cleanup: refusing path outside root: %s", path)
            return False
        if not os.path.exists(path):
            # Already gone — make ``cleanup`` idempotent.
            await self._git("worktree", "prune")
            return True
        if not force and await self.has_changes(path):
            return False
        try:
            await self._git("worktree", "remove", "--force", path)
        except Exception:  # noqa: BLE001
            logger.exception("git worktree remove failed; falling back to rmtree")
            shutil.rmtree(path, ignore_errors=True)
            await self._git("worktree", "prune")
        return True

    async def list(self) -> List[WorktreeInfo]:
        out = await self._git("worktree", "list", "--porcelain")
        infos: List[WorktreeInfo] = []
        path: Optional[str] = None
        branch: Optional[str] = None
        for line in out.splitlines():
            if line.startswith("worktree "):
                if path is not None:
                    infos.append(
                        WorktreeInfo(path=path, branch=branch or "", repo=self._repo)
                    )
                path = line[len("worktree "):].strip()
                branch = None
            elif line.startswith("branch "):
                branch = line[len("branch "):].strip()
        if path is not None:
            infos.append(WorktreeInfo(path=path, branch=branch or "", repo=self._repo))
        return [w for w in infos if self._owned(w.path)]

    # ── Internals ────────────────────────────────────────────────────

    def _owned(self, path: str) -> bool:
        return os.path.abspath(path).startswith(self._root + os.sep)

    async def _is_git_repo(self) -> bool:
        try:
            await self._git("rev-parse", "--git-dir")
            return True
        except Exception:  # noqa: BLE001
            return False

    async def _git(self, *args: str) -> str:
        return await self._git_at(self._repo, *args)

    async def _git_at(self, cwd: str, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} (cwd={cwd}) failed: {stderr.decode().strip()}"
            )
        return stdout.decode("utf-8", errors="replace")
