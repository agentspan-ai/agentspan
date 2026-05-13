"""Verify ``_coder_done`` Layer-2 stall detection.

When the inspection budget gate fires but the model ignores the resulting
blocked tool-result messages (which is the empirical observation — codex
keeps emitting search calls), the agent would otherwise loop to max_turns.
``_coder_done`` now scans recent messages for the blocked sentinel and
terminates hard once enough accumulate. This test exercises that path.
"""

from __future__ import annotations

import sys
from pathlib import Path

EXAMPLES_DIR = (Path(__file__).resolve().parent.parent / "examples").resolve()
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))

# The script registers a CLI in __main__, so we have to import it as a module
# carefully. It guards the CLI execution behind ``if __name__ == "__main__"``,
# so plain import is safe.
import importlib  # noqa: E402

_mod = importlib.import_module("100_issue_fixer_agent")
_coder_done = _mod._coder_done
_count_blocked_tool_messages = _mod._count_blocked_tool_messages
_STALLED_BLOCKED_THRESHOLD = _mod._STALLED_BLOCKED_THRESHOLD
_PROGRESS_DISCOUNT = _mod._PROGRESS_DISCOUNT
_BLOCKED_TOKEN = _mod._BLOCKED_TOKEN


def _progress_marker_message(name: str) -> dict:
    return {
        "role": "tool_call",
        "message": "",
        "toolCalls": [{"name": name, "taskReferenceName": "call_p", "inputParameters": {}}],
    }


def _blocked_tool_message_with_text(text: str) -> dict:
    return {"role": "tool", "message": text, "toolCalls": []}


def _blocked_tool_message_via_output(text: str) -> dict:
    return {
        "role": "tool",
        "message": "",
        "toolCalls": [
            {
                "name": "grep_search",
                "taskReferenceName": "call_xyz",
                "output": {"result": text},
            }
        ],
    }


def _ok_tool_message(text: str) -> dict:
    return {
        "role": "tool",
        "message": text,
        "toolCalls": [],
    }


def test_count_blocked_tool_messages_inline_message() -> None:
    msgs = [
        _ok_tool_message("file contents"),
        _blocked_tool_message_with_text(f"{_BLOCKED_TOKEN} (10 calls). ..."),
        _blocked_tool_message_with_text(f"{_BLOCKED_TOKEN} (10 calls). ..."),
    ]
    assert _count_blocked_tool_messages(msgs) == 2


def test_count_blocked_tool_messages_via_tool_call_output() -> None:
    # The agentspan tool path writes the result into toolCalls[*].output.result
    # — counter must look there too.
    msgs = [
        _blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} (10 calls). ..."),
        _ok_tool_message("file contents"),
        _blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} (10 calls). ..."),
        _blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} (10 calls). ..."),
    ]
    assert _count_blocked_tool_messages(msgs) == 3


def test_count_ignores_non_tool_roles() -> None:
    # System / user / assistant messages should never be counted, even if
    # they accidentally contain the sentinel text.
    msgs = [
        {"role": "system", "message": f"{_BLOCKED_TOKEN} reference"},
        {"role": "user", "message": f"{_BLOCKED_TOKEN} discussed"},
        {"role": "assistant", "message": f"{_BLOCKED_TOKEN} would happen"},
    ]
    assert _count_blocked_tool_messages(msgs) == 0


def test_count_handles_garbage_input() -> None:
    assert _count_blocked_tool_messages(None) == 0
    assert _count_blocked_tool_messages([]) == 0
    assert _count_blocked_tool_messages("not a list") == 0
    assert _count_blocked_tool_messages([{"role": "tool"}]) == 0  # no payload
    assert _count_blocked_tool_messages([{"role": "tool", "toolCalls": [None]}]) == 0


def test_coder_done_fires_on_accumulated_blocked_messages() -> None:
    # Threshold blocked tool results in recent history → stop.
    blocked = [
        _blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} (10 calls). ...")
        for _ in range(_STALLED_BLOCKED_THRESHOLD)
    ]
    ctx = {"result": [], "messages": blocked, "iteration": 7}
    assert _coder_done(ctx) is True, (
        f"once {_STALLED_BLOCKED_THRESHOLD} blocked tool messages accumulate, "
        f"_coder_done MUST return True to terminate the agent"
    )


def test_coder_done_does_not_fire_under_threshold() -> None:
    blocked = [
        _blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} (10 calls). ...")
        for _ in range(_STALLED_BLOCKED_THRESHOLD - 1)
    ]
    ctx = {"result": [], "messages": blocked, "iteration": 7}
    # And the happy-path conditions aren't met either (no contextbook files
    # in this test dir).
    assert _coder_done(ctx) is False, (
        f"with only {_STALLED_BLOCKED_THRESHOLD - 1} blocked messages we should "
        f"keep going — the model still has a chance to recover"
    )


def test_coder_done_unaffected_when_no_messages_supplied() -> None:
    # Backward compat: older runtimes that don't pass ``messages`` should
    # not crash the stop_when.
    ctx = {"result": []}
    assert _coder_done(ctx) is False


# ── Progress-marker discount tests ─────────────────────────────
#
# In execution 8d5fc4fe the agent emitted ``write_coder_context`` at iter 3
# (the "I have a plan" event) and then went back to searching at iter 4-6.
# Layer 2 fired at iter 5 because every blocked message counted equally and
# the threshold was 5. The recalibrated detector subtracts
# ``_PROGRESS_DISCOUNT`` for each progress-marker call, so the agent gets
# extra runway right after writing its plan/report.


def test_progress_marker_discounts_blocked_count() -> None:
    # 8 blocked, 1 write_coder_context → net = 8 - 1×5 = 3, well under
    # threshold of 15. Should NOT count as stalled.
    msgs = [
        *(_blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} ...") for _ in range(4)),
        _progress_marker_message("write_coder_context"),
        *(_blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} ...") for _ in range(4)),
    ]
    net = _count_blocked_tool_messages(msgs)
    assert net == 3, f"expected 3 (8 blocked - 1×5 discount), got {net}"


def test_progress_marker_discount_does_not_go_negative() -> None:
    # 3 blocked, 2 progress markers → 3 - 10 = -7, clamped to 0.
    msgs = [
        _blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} ..."),
        _progress_marker_message("write_coder_context"),
        _blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} ..."),
        _progress_marker_message("write_implementation_report"),
        _blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} ..."),
    ]
    assert _count_blocked_tool_messages(msgs) == 0


def test_coder_done_does_not_fire_when_recent_progress_marker_present() -> None:
    # The 8d5fc4fe pattern: many blocked + 1 write_coder_context. Net count
    # should drop below threshold and _coder_done must NOT terminate.
    msgs = [
        *(_blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} ...") for _ in range(8)),
        _progress_marker_message("write_coder_context"),
        *(_blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} ...") for _ in range(4)),
    ]
    # 12 blocked - 1 progress*5 = 7, under 15.
    assert _coder_done({"result": [], "messages": msgs}) is False, (
        "with a recent write_coder_context, the discount must drop net "
        "blocked below threshold so the agent gets time to act on the plan"
    )


def test_coder_done_still_fires_after_long_stall_even_with_one_progress() -> None:
    # If the agent emits one progress marker and then keeps looping for a
    # long time, the discount should NOT save it indefinitely. 22 blocked,
    # 1 progress = 22 - 5 = 17, exceeds threshold 15 → terminate.
    msgs = [
        _progress_marker_message("write_coder_context"),
        *(_blocked_tool_message_via_output(f"{_BLOCKED_TOKEN} ...") for _ in range(22)),
    ]
    assert _coder_done({"result": [], "messages": msgs}) is True
