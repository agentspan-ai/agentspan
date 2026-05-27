# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the AML investigation loop in example 113.

Pins the pure-function invariants — tool stubs return wrapped ``{"result":
{...}}``, the workflow def has the expected DO_WHILE body with PAC + SUB_WORKFLOW,
the case-file appender preserves the iteration order."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_example():
    py_root = Path(__file__).resolve().parents[2]
    src = py_root / "examples" / "113_aml_sar_investigation_loop.py"
    spec = importlib.util.spec_from_file_location("ex113", src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unwrap(fn):
    return getattr(fn, "__wrapped__", fn)


def test_query_transactions_returns_wrapped_dict_for_known_customer():
    """PAC compiles a sub-workflow that surfaces ``${last_op.output.result}``
    as the sub-workflow's output. If the tool doesn't wrap its return in
    ``{"result": {...}}``, the outer DO_WHILE can't read the verdict and
    the whole loop breaks."""
    ex = _load_example()
    out = _unwrap(ex.query_transactions)("CUST-7821", 30)
    assert "result" in out
    assert "cash_deposits" in out["result"]
    assert len(out["result"]["cash_deposits"]) == 8
    # Every cash deposit should be under the $10K CTR threshold — that's
    # the "structuring" signal the LLM is looking for.
    assert all(d["amount"] < 10000 for d in out["result"]["cash_deposits"])


def test_query_world_check_returns_no_hits_for_clean_entity():
    """Negative findings teach the LLM that absence-of-hits is NOT
    exoneration on its own."""
    ex = _load_example()
    out = _unwrap(ex.query_world_check)("ACME Logistics Inc.")
    assert out["result"]["sanctions_matches"] == []
    assert out["result"]["pep_matches"] == []
    assert out["result"]["adverse_media_count"] == 0


def test_query_adverse_media_returns_typology_match():
    """The adverse-media corpus includes a Reuters article + a FinCEN
    advisory describing the exact typology of the alert. The LLM
    converges on SAR by linking these to the customer's transactions."""
    ex = _load_example()
    out = _unwrap(ex.query_adverse_media)("CUST-7821", "freight forwarding")
    hits = out["result"]["hits"]
    assert len(hits) >= 1
    assert any("FinCEN" in h.get("source", "") for h in hits)


def test_finalize_disposition_emits_done_flag():
    """The DO_WHILE's loopCondition checks
    ``extract_result['result']['finalized'] != true``. The finalize tool
    must set ``finalized: True`` so the loop terminates."""
    ex = _load_example()
    out = _unwrap(ex.finalize_disposition)(
        "sar_eligible",
        "Customer engaged in structuring pattern over 5 days.",
        ["structuring", "high-risk geography"],
        ["transactions:CUST-7821", "adverse_media:CUST-7821"],
    )
    assert out["result"]["finalized"] is True
    assert out["result"]["disposition"] == "sar_eligible"
    assert len(out["result"]["red_flags"]) == 2
    assert len(out["result"]["supporting_evidence"]) == 2


def test_workflow_def_has_do_while_with_real_pac_and_subworkflow():
    """The structural test the user's "I want the loop INSIDE the workflow"
    feedback enforces. The DO_WHILE's body must include both
    PLAN_AND_COMPILE and SUB_WORKFLOW so each iteration is a genuine
    plan-compile-execute turn."""
    ex = _load_example()
    tool_defs = [{"name": "query_kyc_profile", "inputSchema": {}}]
    wf = ex.build_workflow_def(tool_defs)
    assert wf["name"] == "aml_sar_investigation_loop"

    loop = next(t for t in wf["tasks"] if t["type"] == "DO_WHILE")
    types_in_body = [t["type"] for t in loop["loopOver"]]
    assert "LLM_CHAT_COMPLETE" in types_in_body
    assert "PLAN_AND_COMPILE" in types_in_body
    assert "SUB_WORKFLOW" in types_in_body
    # Refs in the order the loop must run them.
    refs = [t["taskReferenceName"] for t in loop["loopOver"]]
    assert refs.index("plan_and_compile") < refs.index("plan_exec")
    assert refs.index("plan_exec") < refs.index("extract_result")


def test_loop_condition_terminates_on_finalized_flag():
    """When the finalize tool runs, the SUB_WORKFLOW output's
    ``result.finalized`` becomes True. The loop's condition must reference
    that via ``$.extract_result['result']['finalized']``."""
    ex = _load_example()
    wf = ex.build_workflow_def([{"name": "x", "inputSchema": {}}])
    loop = next(t for t in wf["tasks"] if t["type"] == "DO_WHILE")
    cond = loop["loopCondition"]
    assert "finalized" in cond
    assert "extract_result" in cond


def test_known_tool_names_are_passed_to_pac_allowlist():
    """PAC rejects plans referencing unknown tools. If we drop a tool
    name from the allowlist, the planner can pick a tool PAC can't
    compile — exactly the hallucinated-tool bug we want to avoid."""
    ex = _load_example()
    tool_defs = [
        {"name": "query_transactions", "inputSchema": {}},
        {"name": "finalize_disposition", "inputSchema": {}},
    ]
    wf = ex.build_workflow_def(tool_defs)
    loop = next(t for t in wf["tasks"] if t["type"] == "DO_WHILE")
    pac = next(t for t in loop["loopOver"] if t["type"] == "PLAN_AND_COMPILE")
    allowlist = pac["inputParameters"]["knownToolNames"]
    assert "query_transactions" in allowlist
    assert "finalize_disposition" in allowlist
