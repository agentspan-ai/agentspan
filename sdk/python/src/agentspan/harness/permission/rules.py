# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Permission rules — structured, source-attributed allow/ask/deny.

Rules are values, not strings. Parsing user-facing rule text into
``PermissionRule`` instances belongs in a separate layer (CLI parser /
config loader) so the engine itself stays decoupled from text formats.

A rule matches a tool call when:

  * ``tool_name == "*"`` OR ``tool_name == call.tool``
  * AND ``pattern is None`` OR the tool's permission matcher (a callable
    the tool may register via ``prepare_permission_matcher``) returns True
    for the rule's pattern.

Each rule carries its ``source`` so audit logs explain why a decision
landed where it did. Source ordering also influences which rule wins on
conflicts:

  policy > project > user > cli > session

— but **deny always beats allow at the same source**.

See ``docs/design/CODING_AGENT_HARNESS_DESIGN.md`` §9.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class RuleSource(str, Enum):
    """Where a rule came from. Higher trust at the top.

    Source values are also used to enforce that a less-trusted source
    cannot override a more-trusted one (e.g. session approval cannot
    bypass a policy deny).
    """

    POLICY = "policy"
    PROJECT = "project"
    USER = "user"
    CLI = "cli"
    SESSION = "session"


class PermissionMode(str, Enum):
    """Effective permission posture for a session.

    - DEFAULT: allow read-only; ask for side effects unless an allow rule matches
    - PLAN: planning + reads only; deny writes/commands until rule allows
    - DONT_ASK: convert any ask result into a deny (headless / autonomous mode)
    - BYPASS: skip ordinary asks; deny rules and safety checks still apply

    v1 ships DEFAULT, PLAN, and DONT_ASK. BYPASS is reserved.
    """

    DEFAULT = "default"
    PLAN = "plan"
    DONT_ASK = "dont_ask"
    BYPASS = "bypass"


@dataclass(frozen=True)
class PermissionRule:
    """One row of the rule table.

    ``pattern`` is opaque to the engine — its meaning is delegated to the
    tool that owns ``tool_name``. For example, the ``shell`` tool may
    interpret it as a glob ``"git status*"`` while ``write_file`` may
    interpret it as a path glob.
    """

    source: RuleSource
    behavior: str  # "allow" | "deny" | "ask"
    tool_name: str  # "*" matches any tool
    pattern: Optional[str] = None
    reason: str = ""


# Tools may register a per-call matcher so a rule's pattern can be
# evaluated against the call. The signature matches the design's
# ``prepare_permission_matcher`` (returns a (pattern → bool) callable).
PermissionMatcher = Callable[[str], bool]
