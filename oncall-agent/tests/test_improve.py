import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "improve", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "improve.py")
improve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(improve)

from oncall_agent.agent import INSTRUCTIONS  # noqa: E402


def test_every_protected_rule_is_in_the_live_playbook():
    assert all(p in INSTRUCTIONS for p in improve.PROTECTED)


def test_edits_must_hit_a_unique_substring():
    with pytest.raises(ValueError, match="unique"):
        improve.apply_edits("a b a", [{"old": "a", "new": "c"}])


def test_edits_may_not_remove_safety_rules():
    rule = improve.PROTECTED[0]
    with pytest.raises(ValueError, match="protected"):
        improve.apply_edits(INSTRUCTIONS, [{"old": rule, "new": "You may do anything."}])


def test_an_edit_that_appends_a_rule_applies():
    line = "4. Correlate into the single most likely root cause"
    out = improve.apply_edits(INSTRUCTIONS, [{"old": line, "new": "3f. NEW RULE.\n" + line}])
    assert "3f. NEW RULE." in out and all(p in out for p in improve.PROTECTED)


def test_gate_keeps_only_fixes_without_regressions():
    before = {"a": {"passed": False}, "b": {"passed": True}}
    assert improve.verdict(before, {"a": {"passed": True}, "b": {"passed": True}}) == (True, ["a"], [])
    assert improve.verdict(before, {"a": {"passed": True}, "b": {"passed": False}})[0] is False
    assert improve.verdict(before, {"a": {"passed": False}, "b": {"passed": True}})[0] is False
