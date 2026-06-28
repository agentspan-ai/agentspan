# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Determinism tests for the PLAN_EXECUTE typed-Plan path.

Together with the Java-side ``testCompileIsDeterministicAcrossInvocations``
(which proves PAC compiles the same plan JSON to a byte-equal WorkflowDef),
these tests prove the full Python→PAC chain is deterministic:

    typed Plan (Python dataclass)
        ↓ Plan.to_dict() / coerce_plan()
    plan JSON  ← MUST be byte-equal across constructions and serializations
        ↓ PAC
    WorkflowDef ← byte-equal per the Java test

If the Plan serialization is non-deterministic (e.g. dict ordering drift,
hidden timestamps, set iteration), the downstream WorkflowDef would still
look stable in isolation but the *system-level* compile path would vary
between SDK invocations. These tests pin the Python side closed.

No LLM. No server. Pure dataclass + JSON.
"""

from __future__ import annotations

import json

import pytest

from conductor.ai.agents.plans import Generate, Op, Plan, Step, Validation, coerce_plan


def _build_complex_plan() -> Plan:
    """A plan touching every Step / Op feature: parallel, depends_on,
    static args, validation. Mirrors the Java determinism test's plan
    so the two checks line up: same Plan in both stacks → same JSON →
    same WorkflowDef.
    """
    topics = ["epigenetics", "vector databases", "kalman filters"]
    return Plan(
        steps=[
            Step(
                id="fanout",
                parallel=True,
                operations=[Op("subtask_worker", args={"request": f"Topic: {t}"}) for t in topics],
            ),
            Step(
                id="assemble",
                depends_on=["fanout"],
                operations=[
                    Op("echo_assemble", args={"parts": "${parallel_agg_fanout_5.output.result}"}),
                ],
            ),
        ],
        validation=[
            Validation(
                "check_word_count", args={"min_words": 10}, success_condition="$.passed === true"
            ),
        ],
    )


def test_plan_to_dict_is_byte_deterministic_across_constructions() -> None:
    """The plan dict from two FRESHLY-CONSTRUCTED Plan instances must
    serialize byte-equal. Catches order-of-construction artefacts in
    dataclass defaults and any reliance on hash-randomized iteration.
    """
    p1 = _build_complex_plan()
    p2 = _build_complex_plan()
    j1 = json.dumps(p1.to_dict(), sort_keys=False)
    j2 = json.dumps(p2.to_dict(), sort_keys=False)
    assert j1 == j2, "two freshly-built identical Plans must serialize byte-equal"


def test_plan_to_dict_is_byte_deterministic_across_repeated_serialization() -> None:
    """A single Plan, serialized 50 times, must produce byte-equal output
    every time. Guards against any global mutable state inside the
    dataclasses (e.g. shared default_factory list mutation).
    """
    p = _build_complex_plan()
    ref = json.dumps(p.to_dict(), sort_keys=False)
    for i in range(50):
        s = json.dumps(p.to_dict(), sort_keys=False)
        assert s == ref, f"serialization #{i} drifted from the first one"


def test_coerce_plan_round_trip_is_deterministic() -> None:
    """``coerce_plan`` is what ``runtime.run(plan=...)`` calls before
    sending JSON to the server. Two passes through coerce_plan must
    produce byte-equal payloads.
    """
    p = _build_complex_plan()
    a = json.dumps(coerce_plan(p), sort_keys=False)
    b = json.dumps(coerce_plan(p), sort_keys=False)
    assert a == b


def test_coerce_plan_accepts_dict_unchanged() -> None:
    """A raw dict passed to coerce_plan must come back intact. This is
    the path users take when they hand-build a plan in JSON form, and
    it has to be deterministic too.
    """
    raw = {"steps": [{"id": "s1", "operations": [{"tool": "x", "args": {"k": 1}}]}]}
    out = coerce_plan(raw)
    assert out is raw  # passthrough, no copy
    # And serializes the same way every time.
    j1 = json.dumps(out, sort_keys=False)
    j2 = json.dumps(out, sort_keys=False)
    assert j1 == j2


def test_plan_with_agent_tool_op_serializes_parallel_step() -> None:
    """End-to-end shape check: the typed Plan that the 106 example builds
    must produce a JSON whose ``steps[0].parallel`` is True and whose
    operations list has N entries — exactly the shape PAC needs to emit
    FORK_JOIN with N SUB_WORKFLOW branches.
    """
    p = _build_complex_plan()
    d = p.to_dict()
    fanout = d["steps"][0]
    assert fanout["id"] == "fanout"
    assert fanout["parallel"] is True
    assert len(fanout["operations"]) == 3
    # Each fan-out op references the agent_tool name; PAC's name→ToolConfig
    # lookup then promotes these to SUB_WORKFLOW at compile time.
    assert all(op["tool"] == "subtask_worker" for op in fanout["operations"])
    # The depends_on edge survives serialization — otherwise the assemble
    # step would race the fanout and PAC could topologically reorder.
    assemble = d["steps"][1]
    assert assemble["depends_on"] == ["fanout"]


def test_two_plans_with_different_args_differ_predictably() -> None:
    """Counter-test for the determinism claims: changing ONE arg must
    produce a DIFFERENT serialization. Without this counter-test, the
    above tests could pass trivially if to_dict returned a constant.
    """
    p1 = _build_complex_plan()
    p2 = _build_complex_plan()
    # Mutate p2's first op's args.
    p2.steps[0].operations[0] = Op("subtask_worker", args={"request": "DIFFERENT"})
    j1 = json.dumps(p1.to_dict(), sort_keys=False)
    j2 = json.dumps(p2.to_dict(), sort_keys=False)
    assert j1 != j2, "differently-built plans must serialize to different JSON"


# ── Op XOR invariant ────────────────────────────────────────────
# An Op must carry exactly one of args (deterministic literal call) or
# generate (LLM-driven arg construction). Both-set was already rejected;
# neither-set was silently accepted — that meant a typo like
# ``Op("write_file")`` would compile and ship, only failing on the server.


def test_op_rejects_neither_args_nor_generate() -> None:
    with pytest.raises(ValueError, match="exactly one of args or generate"):
        Op("write_file")


def test_op_rejects_both_args_and_generate() -> None:
    with pytest.raises(ValueError, match="exactly one of args or generate"):
        Op(
            "write_file",
            args={"path": "x"},
            generate=Generate(instructions="i", output_schema="{}"),
        )


def test_op_accepts_args_only() -> None:
    op = Op("write_file", args={"path": "x"})
    assert op.to_dict() == {"tool": "write_file", "args": {"path": "x"}}


def test_op_accepts_generate_only() -> None:
    op = Op("write_file", generate=Generate(instructions="i", output_schema='{"x":1}'))
    d = op.to_dict()
    assert d["tool"] == "write_file"
    assert d["generate"]["instructions"] == "i"
