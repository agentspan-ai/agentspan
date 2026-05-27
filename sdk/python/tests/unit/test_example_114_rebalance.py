# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the portfolio-rebalance loop in example 114.

Pins the deterministic constraint engine (wash-sale, concentration, drift)
and the workflow shape (DO_WHILE wraps real PAC + SUB_WORKFLOW)."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_example():
    py_root = Path(__file__).resolve().parents[2]
    src = py_root / "examples" / "114_portfolio_rebalance_loop.py"
    spec = importlib.util.spec_from_file_location("ex114", src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check(ex, trades):
    fn = getattr(ex.check_constraints, "__wrapped__", ex.check_constraints)
    return fn(trades, ex.PORTFOLIO["account_id"])["result"]


def test_wash_sale_fires_when_buying_vti():
    """The dg-style verifier signal that drives iteration 2 in the live
    demo. Without this firing, the LLM never substitutes SCHB / ITOT /
    VOO and the loop never demonstrates constraint-driven refinement."""
    ex = _load_example()
    out = _check(ex, [{"action": "buy", "symbol": "VTI", "shares": 100}])
    types = {v["type"] for v in out["violations"]}
    assert "wash_sale_violation" in types


def test_restricted_symbol_fires_for_tsla_and_mo():
    ex = _load_example()
    for sym in ("TSLA", "MO"):
        out = _check(ex, [{"action": "buy", "symbol": sym, "shares": 1}])
        types = {v["type"] for v in out["violations"]}
        assert "restricted_symbol" in types, f"missed restricted_symbol for {sym}"


def test_substitute_schb_clears_wash_sale():
    """SCHB is the canonical broad-market substitute when VTI is locked.
    The LLM's iteration N+1 prompt explicitly steers toward SCHB; if our
    pricing table gets SCHB wrong (or the asset_class mapping breaks),
    the substitute path stops working."""
    ex = _load_example()
    out = _check(
        ex,
        [
            {"action": "sell", "symbol": "BND", "shares": 300},
            {"action": "buy", "symbol": "SCHB", "shares": 1250},
        ],
    )
    types = {v["type"] for v in out["violations"]}
    assert "wash_sale_violation" not in types


def test_starting_portfolio_has_drift_above_tolerance():
    """The demo only iterates if the starting state has work to do."""
    ex = _load_example()
    cw = ex._current_weights(ex.PORTFOLIO)
    target = ex.PORTFOLIO["target_weights"]
    drifts_bps = [abs(cw[ac] - target[ac]) * 10000 for ac in target]
    assert max(drifts_bps) > ex.PORTFOLIO["restrictions"]["drift_tolerance_bps"]


def test_submit_trades_flips_submitted_flag():
    """The DO_WHILE's loopCondition exits when submit's output.result.submitted
    is true. The tool must set it."""
    ex = _load_example()
    fn = getattr(ex.submit_trades, "__wrapped__", ex.submit_trades)
    out = fn([{"action": "sell", "symbol": "BND", "shares": 200}], "ACCT-9301", "rationale")
    assert out["result"]["submitted"] is True
    assert out["result"]["drift_within_tolerance"] is True


def test_oversell_violation_when_selling_more_than_held():
    """Catches an LLM that proposes selling more shares than the
    portfolio holds — a class of error that's invisible without
    deterministic checks."""
    ex = _load_example()
    held = ex.PORTFOLIO["current_holdings"]["AAPL"]["shares"]
    out = _check(ex, [{"action": "sell", "symbol": "AAPL", "shares": held + 100}])
    assert any(v["type"] == "oversell" for v in out["violations"])


def test_workflow_def_has_pac_and_subworkflow_in_loop():
    ex = _load_example()
    tool_defs = [{"name": "check_constraints", "inputSchema": {}}]
    wf = ex.build_workflow_def(tool_defs)
    loop = next(t for t in wf["tasks"] if t["type"] == "DO_WHILE")
    types_in_body = [t["type"] for t in loop["loopOver"]]
    assert "PLAN_AND_COMPILE" in types_in_body
    assert "SUB_WORKFLOW" in types_in_body
    refs = [t["taskReferenceName"] for t in loop["loopOver"]]
    assert refs.index("plan_and_compile") < refs.index("plan_exec")


def test_loop_condition_terminates_on_submitted():
    """The DO_WHILE exit signal is submit_trades's output.result.submitted.
    Regressing this would loop forever or until budget exhausted."""
    ex = _load_example()
    wf = ex.build_workflow_def([{"name": "submit_trades", "inputSchema": {}}])
    loop = next(t for t in wf["tasks"] if t["type"] == "DO_WHILE")
    assert "submitted" in loop["loopCondition"]
    assert "extract_result" in loop["loopCondition"]


def test_drift_within_tolerance_after_known_clean_rebalance():
    """The deterministic constraint engine's drift calculation must agree
    with manual arithmetic. Pin a hand-computed scenario."""
    ex = _load_example()
    # Sell 300 BND ($21.9K from bonds) and buy 1250 SCHB ($30K to broad)
    out = _check(
        ex,
        [
            {"action": "sell", "symbol": "BND", "shares": 300},
            {"action": "buy", "symbol": "SCHB", "shares": 1250},
        ],
    )
    # Should clear all constraint types except possibly drift (which
    # depends on exact share counts).
    types = {v["type"] for v in out["violations"]}
    assert "wash_sale_violation" not in types
    assert "restricted_symbol" not in types
    assert "concentration_violation" not in types
    # The 1250-SCHB-and-300-BND combo lands inside the 300 bps tolerance.
    assert out["drift_within_tolerance"] is True
