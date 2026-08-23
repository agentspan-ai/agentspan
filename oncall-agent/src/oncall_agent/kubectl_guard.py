"""Deterministic read-only guard for kubectl commands.

KUBECTL_UNRESTRICTED executes whatever it is given inside the customer cluster,
so — exactly like ``sql_guard`` — the guard, not the model, decides what may
run. Allowlist of read verbs; ``rollout`` is allowed only for its read
subcommands; shell metacharacters are rejected outright (the worker hands the
command to a shell, so chaining/subshells must never pass).
"""
from __future__ import annotations

_READ_VERBS = {
    "get",
    "describe",
    "logs",
    "top",
    "explain",
    "version",
    "api-resources",
    "api-versions",
    "cluster-info",
    "auth",  # `auth can-i` — read-only self-check
}
_ROLLOUT_READ_SUBCOMMANDS = {"history", "status"}
_SHELL_METACHARACTERS = set(";|&`$<>")


class NotReadOnlyKubectlError(Exception):
    """The command is not provably read-only."""


def ensure_readonly_kubectl(command: str) -> str:
    """Return the cleaned command if read-only; raise otherwise."""
    cleaned = (command or "").strip()
    if cleaned.lower().startswith("kubectl"):
        cleaned = cleaned[len("kubectl"):].strip()
    if not cleaned:
        raise NotReadOnlyKubectlError("empty kubectl command")

    bad = _SHELL_METACHARACTERS.intersection(cleaned)
    if bad:
        raise NotReadOnlyKubectlError(
            f"shell metacharacter(s) {sorted(bad)} not allowed in kubectl commands"
        )

    parts = cleaned.split()
    verb = parts[0].lower()
    if verb == "rollout":
        sub = parts[1].lower() if len(parts) > 1 else ""
        if sub not in _ROLLOUT_READ_SUBCOMMANDS:
            raise NotReadOnlyKubectlError(
                f"rollout subcommand {sub!r} mutates state; only "
                f"{sorted(_ROLLOUT_READ_SUBCOMMANDS)} are allowed"
            )
        return cleaned
    if verb not in _READ_VERBS:
        raise NotReadOnlyKubectlError(
            f"kubectl verb {verb!r} is not in the read-only allowlist {sorted(_READ_VERBS)}"
        )
    return cleaned
