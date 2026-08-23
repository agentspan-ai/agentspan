"""Deterministic read-only SQL guard.

The on-call agent may run SELECT-only queries against the cluster Conductor DB
(via the ``sql_conductor`` agent-handler workflow). Enforcement must NOT depend on
the LLM behaving — this module is the single gate every query passes through before
dispatch. It rejects anything that could mutate state or smuggle a second statement.

The policy is intentionally strict: a false rejection of an unusual-but-valid read
query is acceptable; allowing a mutation is not.
"""
from __future__ import annotations

import re


class NotReadOnlySQLError(ValueError):
    """Raised when a query is not a single, read-only statement."""


# Allowed leading keyword of the (single) statement.
_ALLOWED_LEADERS = ("select", "with", "explain", "show", "table", "values")

# Keywords that can mutate data/schema/session, or run procedural code. Matched as
# whole words anywhere in the comment-stripped query, so a mutation hidden inside a
# CTE (e.g. ``WITH x AS (DELETE ... RETURNING *)``) is still caught.
_FORBIDDEN = frozenset(
    {
        "insert", "update", "delete", "drop", "alter", "create", "truncate",
        "replace", "merge", "upsert", "grant", "revoke", "call", "do", "copy",
        "vacuum", "analyze", "reindex", "cluster", "lock", "set", "reset",
        "begin", "start", "commit", "rollback", "savepoint", "comment",
        "refresh", "import", "load", "attach", "detach", "pragma", "exec",
        "execute", "prepare", "deallocate", "listen", "notify", "discard",
    }
)

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _strip_comments(sql: str) -> str:
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    return sql


def ensure_select(query: str) -> str:
    """Return the normalised query if it is a single read-only statement.

    Raises :class:`NotReadOnlySQLError` otherwise. ``EXPLAIN`` / ``SHOW`` /
    ``WITH ... SELECT`` are allowed; multiple statements, comment-hidden statements,
    and any DML/DDL/session-changing keyword are rejected.
    """
    if not query or not query.strip():
        raise NotReadOnlySQLError("empty query")

    stripped = _strip_comments(query).strip()
    if not stripped:
        raise NotReadOnlySQLError("query is only comments")

    # Allow exactly one optional trailing ';'. Any other ';' implies a second
    # statement and is rejected.
    body = stripped.rstrip().rstrip(";").rstrip()
    if ";" in body:
        raise NotReadOnlySQLError("multiple statements are not allowed")

    tokens = [t.lower() for t in _WORD.findall(body)]
    if not tokens:
        raise NotReadOnlySQLError("no SQL keywords found")

    if tokens[0] not in _ALLOWED_LEADERS:
        raise NotReadOnlySQLError(
            f"query must start with one of {_ALLOWED_LEADERS}, got '{tokens[0]}'"
        )

    forbidden = sorted({t for t in tokens if t in _FORBIDDEN})
    if forbidden:
        raise NotReadOnlySQLError(f"forbidden keyword(s) present: {', '.join(forbidden)}")

    return body
