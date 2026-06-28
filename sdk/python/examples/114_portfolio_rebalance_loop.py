#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""114 — Wealth-management portfolio rebalancing loop with real PAC + SUB_WORKFLOW.

An RIA portfolio is off target. Each iteration the planner LLM proposes a
trade list; PAC compiles a one-step plan that runs the deterministic
``check_constraints`` engine; the result tells the LLM exactly which
compliance / tax / drift constraints fired; the LLM refines its proposal
on the next turn. When all constraints clear AND drift is within tolerance,
the planner calls ``submit_trades`` and the DO_WHILE exits.

This is the portfolio-rebalancing variant of the PAE-loop pattern in
example 113 — but where AML's iteration is *meta-planning* (which
evidence to query next), here the iteration is *constraint-driven
refinement* (substitute this trade so the wash-sale rule clears).

Constraints applied per proposal:
  * concentration: no single position > 15% of portfolio value
  * restricted list: no trades in {TSLA, MO} per client mandate / ESG
  * wash-sale window: cannot purchase {VTI} for 30 days after recent sale
  * drift tolerance: post-trade asset-class weights within ±50 bps of target

What you'll see:
  * ONE workflow ID for the whole rebalancing session.
  * Per-iteration suffixes (planner_llm__1, plan_and_compile__1, ...).
  * The check_constraints sub-workflow runs each turn against the
    proposed trades; its structured violation list drives the next plan.
  * Termination on the iteration where submit_trades is called.

Requirements:
  - AGENTSPAN_SERVER_URL=http://localhost:6767/api (default)
  - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini (default)
  - LLM key for the chosen model.
"""

import json
import os
import re
import sys
import time

import requests

from conductor.ai.agents import AgentRuntime, plan_execute, tool

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE = SERVER_URL.rstrip("/").replace("/api", "")
MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6")
MAX_ITER = int(os.environ.get("AGENTSPAN_REBAL_MAX_ITER", "8"))
WORKFLOW_NAME = "portfolio_rebalance_loop"
WORKFLOW_VERSION = 6


def _model_split(model: str) -> tuple[str, str]:
    if "/" in model:
        provider, name = model.split("/", 1)
        return provider, name
    return "openai", model


PROVIDER, MODEL_NAME = _model_split(MODEL)


# ── Synthetic portfolio + constraints ─────────────────────────────


PORTFOLIO = {
    "account_id": "ACCT-9301",
    "client": "Jane Smith Trust",
    # Stocks_us_large and alternatives at target; bonds OVER target (+1000 bps);
    # stocks_us_broad UNDER target (-1000 bps). The obvious rebalance — sell
    # BND, buy VTI — hits the wash-sale rule, forcing a substitution to
    # SCHB/ITOT/VOO. Drift tolerance is generous (300 bps) so a roughly
    # right trade clears it; precise share-counting isn't the demo's point.
    "current_holdings": {
        "AAPL": {"shares": 230, "price": 220.0, "asset_class": "stocks_us_large"},
        "MSFT": {"shares": 95,  "price": 425.0, "asset_class": "stocks_us_large"},
        "NVDA": {"shares": 32,  "price": 920.0, "asset_class": "stocks_us_large"},
        "VTI":  {"shares": 225, "price": 268.0, "asset_class": "stocks_us_broad"},
        "BND":  {"shares": 1450,"price": 73.0,  "asset_class": "bonds"},
        "GLD":  {"shares": 60,  "price": 245.0, "asset_class": "alternatives"},
    },
    "target_weights": {
        "stocks_us_large": 0.40,
        "stocks_us_broad": 0.30,
        "bonds":           0.25,
        "alternatives":    0.05,
    },
    "restrictions": {
        "restricted_symbols": ["TSLA", "MO"],
        "max_position_pct": 0.30,
        "wash_sale_window_symbols": ["VTI"],
        "drift_tolerance_bps": 300,
    },
}


# Total portfolio value (for percent calcs).
def _portfolio_value(holdings: dict) -> float:
    return sum(h["shares"] * h["price"] for h in holdings.values())


# Current asset-class weights (used in the planner prompt to make the
# drift visible without burdening the LLM with arithmetic).
def _current_weights(p: dict) -> dict:
    tv = _portfolio_value(p["current_holdings"])
    if tv == 0:
        return {ac: 0.0 for ac in p["target_weights"]}
    weights: dict = {}
    for symbol, h in p["current_holdings"].items():
        ac = h["asset_class"]
        weights[ac] = weights.get(ac, 0.0) + (h["shares"] * h["price"]) / tv
    # Make sure every target class is represented (even if 0).
    for ac in p["target_weights"]:
        weights.setdefault(ac, 0.0)
    return weights


# ── Tools ────────────────────────────────────────────────────────


@tool
def check_constraints(trades: list, account_id: str) -> dict:
    """Apply concentration + restricted-list + wash-sale + drift checks to
    a candidate trade list. Returns a structured violation report.

    Each trade is shape:
      {"action": "buy"|"sell", "symbol": "AAPL", "shares": 100}

    Wrapped in ``{"result": {...}}`` so PAC's compiled-workflow
    ``outputParameters`` (which references ``${last_op.output.result}``)
    surfaces the report to the outer DO_WHILE.
    """
    # The portfolio is held in module state for the demo. A real
    # deployment would look it up by account_id.
    p = PORTFOLIO
    restrictions = p["restrictions"]
    holdings = {s: dict(h) for s, h in p["current_holdings"].items()}

    violations = []
    parsed_trades = []
    for t in trades or []:
        try:
            action = t.get("action")
            symbol = t.get("symbol")
            shares = int(t.get("shares", 0))
        except (AttributeError, TypeError, ValueError):
            violations.append(
                {"type": "malformed_trade", "trade": t, "detail": "could not parse trade"}
            )
            continue
        if action not in {"buy", "sell"} or not symbol or shares <= 0:
            violations.append(
                {
                    "type": "malformed_trade",
                    "trade": t,
                    "detail": "need action in {buy,sell}, symbol, shares>0",
                }
            )
            continue
        parsed_trades.append({"action": action, "symbol": symbol, "shares": shares})

        # Restricted-list check
        if symbol in restrictions["restricted_symbols"]:
            violations.append(
                {
                    "type": "restricted_symbol",
                    "symbol": symbol,
                    "detail": f"{symbol} is on the client's restricted list "
                    f"({restrictions['restricted_symbols']}); no trade allowed.",
                }
            )
        # Wash-sale check (applies to buys only)
        if action == "buy" and symbol in restrictions["wash_sale_window_symbols"]:
            violations.append(
                {
                    "type": "wash_sale_violation",
                    "symbol": symbol,
                    "detail": (
                        f"{symbol} sold within last 30 days; repurchase would create "
                        "an IRS Section 1091 wash-sale loss-disallowance. Substitute "
                        "a similar-but-not-identical security (e.g. SCHB or ITOT for VTI)."
                    ),
                }
            )

    # Simulate post-trade holdings (only for non-malformed trades that
    # otherwise pass the per-trade gates above — we still simulate
    # to compute drift, even if a constraint fired).
    post = {s: dict(h) for s, h in holdings.items()}
    for t in parsed_trades:
        symbol = t["symbol"]
        if symbol not in post:
            # Buying a new symbol — assume current_price market quote.
            # In a real system we'd hit market data; here we lookup a
            # tiny synthetic price table.
            price = {"ITOT": 122.0, "SCHB": 24.0, "VOO": 510.0, "VEA": 53.0}.get(symbol, 100.0)
            asset_class = (
                "stocks_us_broad"
                if symbol in {"ITOT", "SCHB", "VOO"}
                else "stocks_intl"
                if symbol == "VEA"
                else "stocks_us_large"
            )
            post[symbol] = {"shares": 0, "price": price, "asset_class": asset_class}
        if t["action"] == "buy":
            post[symbol]["shares"] += t["shares"]
        else:
            post[symbol]["shares"] -= t["shares"]
            if post[symbol]["shares"] < 0:
                violations.append(
                    {
                        "type": "oversell",
                        "symbol": symbol,
                        "detail": f"sell of {t['shares']} shares of {symbol} exceeds current position.",
                    }
                )

    total_value = sum(h["shares"] * h["price"] for h in post.values())
    # Concentration check on post-trade holdings.
    if total_value > 0:
        for symbol, h in post.items():
            if h["shares"] <= 0:
                continue
            pct = (h["shares"] * h["price"]) / total_value
            if pct > restrictions["max_position_pct"]:
                violations.append(
                    {
                        "type": "concentration_violation",
                        "symbol": symbol,
                        "detail": (
                            f"post-trade {symbol} would be {pct * 100:.1f}% of portfolio, "
                            f"exceeding the {restrictions['max_position_pct'] * 100:.0f}% per-position limit."
                        ),
                    }
                )

    # Drift from target.
    post_weights: dict = {}
    if total_value > 0:
        for h in post.values():
            ac = h["asset_class"]
            post_weights[ac] = post_weights.get(ac, 0.0) + (h["shares"] * h["price"]) / total_value
    target = p["target_weights"]
    drift_bps_per_class = {}
    for ac, w in target.items():
        actual = post_weights.get(ac, 0.0)
        drift_bps_per_class[ac] = round((actual - w) * 10000, 1)
    max_abs_drift_bps = max((abs(v) for v in drift_bps_per_class.values()), default=0.0)
    drift_within_tolerance = max_abs_drift_bps <= restrictions["drift_tolerance_bps"]
    if not drift_within_tolerance:
        violations.append(
            {
                "type": "drift_above_tolerance",
                "detail": (
                    f"max asset-class drift is {max_abs_drift_bps:.0f} bps "
                    f"(tolerance {restrictions['drift_tolerance_bps']} bps). Drifts: "
                    f"{drift_bps_per_class}"
                ),
            }
        )

    return {
        "result": {
            "submitted": False,
            "violations": violations,
            "violation_count": len(violations),
            "post_trade_weights": post_weights,
            "drift_bps": drift_bps_per_class,
            "max_drift_bps": max_abs_drift_bps,
            "drift_within_tolerance": drift_within_tolerance,
            "post_trade_holdings": post,
        }
    }


@tool
def submit_trades(trades: list, account_id: str, rationale: str = "") -> dict:
    """Submit a clean trade list. ``submitted: true`` flips the DO_WHILE's
    termination flag.
    """
    return {
        "result": {
            "submitted": True,
            "violations": [],
            "violation_count": 0,
            "trades": trades or [],
            "rationale": rationale,
            "drift_within_tolerance": True,
            "account_id": account_id,
        }
    }


TOOLS_LIST = [check_constraints, submit_trades]


# ── INLINE script bodies (GraalJS) ────────────────────────────────


# Walk a Conductor Java Map / List into a JS-native object. INLINEs
# that build JSON from upstream ``${task.output.X}`` need this — see
# the same helper in example 113.
TO_JS_OBJ_JS = (
    "function toJSObj(v) {"
    "  if (v === null || v === undefined) return v;"
    "  if (typeof v !== 'object') return v;"
    "  if (typeof v.keySet === 'function' && typeof v.get === 'function') {"
    "    var out = {};"
    "    var it = v.keySet().iterator();"
    "    while (it.hasNext()) { var k = it.next(); out[String(k)] = toJSObj(v.get(k)); }"
    "    return out;"
    "  }"
    "  if (typeof v.iterator === 'function' && typeof v.size === 'function'"
    "      && typeof v.keySet !== 'function') {"
    "    var arr = [];"
    "    var lit = v.iterator();"
    "    while (lit.hasNext()) arr.push(toJSObj(lit.next()));"
    "    return arr;"
    "  }"
    "  if (Array.isArray(v)) return v.map(toJSObj);"
    "  var keys = Object.keys(v);"
    "  var out2 = {};"
    "  for (var i = 0; i < keys.length; i++) out2[keys[i]] = toJSObj(v[keys[i]]);"
    "  return out2;"
    "}"
)


EXTRACT_ACTION_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  var r = $.llm_out;"
    "  if (r === null || r === undefined) return null;"
    "  if (typeof r === 'object') return toJSObj(r);"
    "  var s = String(r);"
    "  var m = s.match(/\\{[\\s\\S]*\\}/);"
    "  if (!m) return null;"
    "  try { return JSON.parse(m[0]); }"
    "  catch (e) { return null; }"
    "})();"
)


# Wrap the planner's action into a one-step plan PAC can compile.
# If the LLM provides neither a recognized tool nor a trades list, fall
# back to a no-op ``check_constraints`` with empty trades (which will
# always report "drift_above_tolerance" and ensure the loop keeps going).
BUILD_PLAN_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  var raw = $.action;"
    "  var a;"
    "  if (raw === null || raw === undefined) a = {};"
    "  else if (typeof raw === 'string') {"
    "    try { a = JSON.parse(raw); } catch(e) { a = {}; }"
    "  } else { a = toJSObj(raw); }"
    "  var tool = a.tool || 'check_constraints';"
    "  var args = a.args || {};"
    "  if (!args.account_id) args.account_id = $.account_id;"
    "  if (!args.trades) args.trades = [];"
    "  var plan = {steps: [{id: 'step', operations: [{tool: tool, args: args}]}]};"
    "  return JSON.stringify(plan);"
    "})();"
)


EXTRACT_RESULT_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  var ex = $.exec_output;"
    "  if (!ex) return {submitted: false, violations: [{type: 'no_exec_output'}], "
    "                   violation_count: 1, drift_within_tolerance: false};"
    "  var result = ex.result;"
    "  if (result && typeof result === 'object') return toJSObj(result);"
    "  if (typeof result === 'string') {"
    "    try { return JSON.parse(result); } catch(e) {}"
    "  }"
    "  return {submitted: false, violations: [{type: 'unparseable_result'}], "
    "          violation_count: 1, drift_within_tolerance: false};"
    "})();"
)


# Build a human-readable summary string for the workflow's top-level
# ``output.result`` field. Conductor's UI prefers a leading ``result``
# string over deeply nested output objects; without this the rebalancing
# outcome is invisible in the workflow-detail panel.
SUMMARIZE_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  var fs = $.final_state ? toJSObj($.final_state) : {};"
    "  var n = $.iter_count;"
    "  var lines = [];"
    "  lines.push('Portfolio rebalance — ' + (fs.account_id || ''));"
    "  lines.push('Iterations: ' + n);"
    "  if (fs.submitted === true) {"
    "    lines.push('Status: SUBMITTED');"
    "    var trades = fs.trades || [];"
    "    lines.push('Trades (' + trades.length + '):');"
    "    for (var i = 0; i < trades.length; i++) {"
    "      var t = trades[i] || {};"
    "      lines.push('  - ' + String(t.action || '?').toUpperCase() + ' ' +"
    "                 t.shares + ' ' + t.symbol);"
    "    }"
    "    if (fs.rationale) { lines.push(''); lines.push('Rationale: ' + fs.rationale); }"
    "  } else {"
    "    lines.push('Status: NOT SUBMITTED (budget exhausted)');"
    "    lines.push('Remaining violations: ' + (fs.violation_count || '?'));"
    "    if (fs.max_drift_bps !== undefined) {"
    "      lines.push('Max drift: ' + fs.max_drift_bps + ' bps');"
    "    }"
    "  }"
    "  return lines.join('\\n');"
    "})();"
)


APPEND_HISTORY_JS = TO_JS_OBJ_JS + (
    "(function() {"
    "  function unwrap(v) {"
    "    if (v === null || v === undefined) return null;"
    "    if (typeof v === 'string') {"
    "      try { return JSON.parse(v); } catch(e) { return v; }"
    "    }"
    "    return toJSObj(v);"
    "  }"
    "  var h = unwrap($.history) || [];"
    "  if (!Array.isArray(h)) h = [];"
    "  var act = unwrap($.action) || {};"
    "  var res = unwrap($.result) || {};"
    "  h.push({"
    "    iter: $.iter,"
    "    tool: act.tool || '<unknown>',"
    "    proposed_trades: (act.args || {}).trades || [],"
    "    violation_count: res.violation_count || 0,"
    "    violations: res.violations || [],"
    "    max_drift_bps: res.max_drift_bps,"
    "    submitted: res.submitted || false"
    "  });"
    "  return h;"
    "})();"
)


# ── Planner prompt ───────────────────────────────────────────────


PLANNER_SYSTEM = (
    "You are a portfolio-rebalancing assistant for a Registered Investment "
    "Adviser. The client's account is currently off-target. Each iteration "
    "you propose a trade list; a deterministic constraint engine reports "
    "the exact violations (concentration, restricted list, wash-sale, "
    "drift). Use that feedback to refine your next proposal. When all "
    "constraints clear and drift is within tolerance, call submit_trades.\n\n"
    "Respond with ONLY a JSON object (no prose, no markdown fences):\n\n"
    "  Iterate:\n"
    "  {\"tool\": \"check_constraints\", \"args\": {\"trades\": ["
    "    {\"action\": \"buy\"|\"sell\", \"symbol\": \"<sym>\", \"shares\": <int>}, ...]}}\n\n"
    "  Submit:\n"
    "  {\"tool\": \"submit_trades\", \"args\": {\"trades\": [...], "
    "    \"rationale\": \"<one-sentence why these trades + how violations were resolved>\"}}\n\n"
    "Constraints in force:\n"
    "  - max_position_pct: 30% of portfolio value per symbol\n"
    "  - restricted_symbols: [\"TSLA\", \"MO\"] — no trades in these allowed\n"
    "  - wash_sale_window_symbols: [\"VTI\"] — cannot BUY VTI for 30 days "
    "    (substitute SCHB @ ~$24, ITOT @ ~$122, or VOO @ ~$510 for similar "
    "    stocks_us_broad exposure)\n"
    "  - drift_tolerance_bps: 300 — post-trade asset-class weights must be "
    "    within ±300 basis points of target\n\n"
    "Approximate current market prices (use for share-count math):\n"
    "  AAPL $220, MSFT $425, NVDA $920, VTI $268, BND $73, GLD $245,\n"
    "  SCHB $24, ITOT $122, VOO $510.\n\n"
    "Sizing rule of thumb: shares ≈ (dollars to move) / (symbol price). "
    "If the drift report says stocks_us_broad is -1000 bps on a $300K "
    "portfolio, that's $30K to add — about 1250 shares of SCHB at $24.\n\n"
    "Do not propose the same violating trade twice. When violations point "
    "to a specific substitute (e.g. 'substitute SCHB for VTI'), USE that "
    "substitute on the next pass.\n\n"
    "IMPORTANT TERMINATION RULE: if the most recent history entry shows "
    "violation_count: 0 AND drift_within_tolerance is true, you MUST emit "
    "submit_trades on this turn with the same trade list. Do not re-check "
    "a trade list that already cleared all gates."
)


PLANNER_USER_TEMPLATE = (
    "Iteration: ${loop.output.iteration}.\n"
    "Account: ${workflow.input.account_id}.\n"
    "Current holdings (symbol, shares, price, asset_class):\n"
    "${workflow.input.holdings_json}\n\n"
    "Target asset-class weights:\n"
    "${workflow.input.target_weights_json}\n\n"
    "Current weights:\n"
    "${workflow.input.current_weights_json}\n\n"
    "History of your prior proposals + the constraint engine's responses:\n"
    "${workflow.variables.history}\n\n"
    "Propose the next trade list. Emit ONLY the JSON object."
)


# ── Workflow definition ───────────────────────────────────────────


def build_workflow_def(tool_defs: list[dict]) -> dict:
    parent_tools = list(tool_defs)
    known_tool_names = [t["name"] for t in tool_defs]

    return {
        "name": WORKFLOW_NAME,
        "version": WORKFLOW_VERSION,
        "description": "Portfolio rebalancing — DO_WHILE wraps PAC + SUB_WORKFLOW",
        "tasks": [
            {
                "name": "SET_VARIABLE",
                "taskReferenceName": "init",
                "type": "SET_VARIABLE",
                "inputParameters": {
                    "account_id": "${workflow.input.account_id}",
                    "history": [],
                },
            },
            {
                "name": "DO_WHILE",
                "taskReferenceName": "loop",
                "type": "DO_WHILE",
                "inputParameters": {
                    "loop": "${loop}",
                    "extract_result": "${extract_result}",
                },
                "loopCondition": (
                    f"if ($.loop['iteration'] < {MAX_ITER} "
                    f"&& $.extract_result['result']['submitted'] != true) "
                    f"{{ true; }} else {{ false; }}"
                ),
                "loopOver": [
                    {
                        "name": "LLM_CHAT_COMPLETE",
                        "taskReferenceName": "planner_llm",
                        "type": "LLM_CHAT_COMPLETE",
                        "inputParameters": {
                            "llmProvider": PROVIDER,
                            "model": MODEL_NAME,
                            "maxTokens": 800,
                            "messages": [
                                {"role": "system", "message": PLANNER_SYSTEM},
                                {"role": "user", "message": PLANNER_USER_TEMPLATE},
                            ],
                        },
                    },
                    {
                        "name": "INLINE",
                        "taskReferenceName": "extract_action",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": EXTRACT_ACTION_JS,
                            "llm_out": "${planner_llm.output.result}",
                        },
                    },
                    {
                        "name": "INLINE",
                        "taskReferenceName": "build_plan",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": BUILD_PLAN_JS,
                            "action": "${extract_action.output.result}",
                            "account_id": "${workflow.variables.account_id}",
                        },
                    },
                    {
                        "name": "plan_and_compile",
                        "taskReferenceName": "plan_and_compile",
                        "type": "PLAN_AND_COMPILE",
                        "inputParameters": {
                            "planJson": "${build_plan.output.result}",
                            "parentName": WORKFLOW_NAME,
                            "model": MODEL,
                            "knownToolNames": known_tool_names,
                            "parentTools": parent_tools,
                        },
                    },
                    {
                        "name": "SUB_WORKFLOW",
                        "taskReferenceName": "plan_exec",
                        "type": "SUB_WORKFLOW",
                        "subWorkflowParam": {
                            "name": f"pe_{WORKFLOW_NAME}_plan",
                            "version": 1,
                            "workflowDefinition": "${plan_and_compile.output.workflowDef}",
                        },
                        "inputParameters": {
                            "prompt": "${workflow.input.account_id}",
                        },
                        "optional": True,
                    },
                    {
                        "name": "INLINE",
                        "taskReferenceName": "extract_result",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": EXTRACT_RESULT_JS,
                            "exec_output": "${plan_exec.output}",
                        },
                    },
                    {
                        "name": "INLINE",
                        "taskReferenceName": "append_history",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": APPEND_HISTORY_JS,
                            "history": "${workflow.variables.history}",
                            "iter": "${loop.output.iteration}",
                            "action": "${extract_action.output.result}",
                            "result": "${extract_result.output.result}",
                        },
                    },
                    {
                        "name": "SET_VARIABLE",
                        "taskReferenceName": "update_state",
                        "type": "SET_VARIABLE",
                        "inputParameters": {
                            "history": "${append_history.output.result}",
                            "account_id": "${workflow.variables.account_id}",
                        },
                    },
                ],
            },
            # Post-loop: build a human-readable summary so Conductor UIs
            # render the rebalance outcome prominently in their workflow-detail
            # panel (most UIs key off ``output.result``).
            {
                "name": "INLINE",
                "taskReferenceName": "summarize",
                "type": "INLINE",
                "inputParameters": {
                    "evaluatorType": "graaljs",
                    "expression": SUMMARIZE_JS,
                    "final_state": "${extract_result.output.result}",
                    "iter_count": "${loop.output.iteration}",
                },
            },
        ],
        "inputParameters": [
            "account_id",
            "holdings_json",
            "target_weights_json",
            "current_weights_json",
        ],
        "outputParameters": {
            "result": "${summarize.output.result}",
            "iterations": "${loop.output.iteration}",
            "final_state": "${extract_result.output.result}",
            "history": "${workflow.variables.history}",
        },
        "schemaVersion": 2,
        "ownerEmail": "demo@example.com",
    }


# ── Server interactions ───────────────────────────────────────────


def register_workflow(wf: dict) -> None:
    r = requests.post(
        f"{BASE}/api/metadata/workflow",
        json=[wf],
        headers={"Content-Type": "application/json"},
    )
    if r.status_code not in (200, 204):
        r2 = requests.put(
            f"{BASE}/api/metadata/workflow",
            json=[wf],
            headers={"Content-Type": "application/json"},
        )
        if r2.status_code not in (200, 204):
            raise RuntimeError(
                f"workflow registration failed: POST {r.status_code} {r.text}; "
                f"PUT {r2.status_code} {r2.text}"
            )


def start_execution(portfolio: dict) -> str:
    payload = {
        "account_id": portfolio["account_id"],
        "holdings_json": json.dumps(portfolio["current_holdings"], indent=2),
        "target_weights_json": json.dumps(portfolio["target_weights"], indent=2),
        "current_weights_json": json.dumps(_current_weights(portfolio), indent=2),
    }
    r = requests.post(
        f"{BASE}/api/workflow/{WORKFLOW_NAME}?version={WORKFLOW_VERSION}",
        json=payload,
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    return r.text.strip().strip('"')


def poll_until_done(execution_id: str, timeout: int = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{BASE}/api/workflow/{execution_id}?includeTasks=true")
        r.raise_for_status()
        wf = r.json()
        if wf.get("status") in ("COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"):
            return wf
        time.sleep(2)
    raise TimeoutError(f"workflow {execution_id} did not complete in {timeout}s")


# ── Pretty printing ──────────────────────────────────────────────


def _parse_maybe(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, ValueError):
            return {}
    return v or {}


def print_rebalance_trace(wf: dict) -> None:
    tasks = wf.get("tasks", [])
    suffix_re = re.compile(r"^(.+?)__(\d+)$")
    by_iter: dict[int, dict] = {}
    for t in tasks:
        m = suffix_re.match(t.get("referenceTaskName", ""))
        if not m:
            continue
        base, n = m.group(1), int(m.group(2))
        by_iter.setdefault(n, {})[base] = t

    print(f"{'iter':>5}  {'tool':<20}  {'trades':<40}  {'outcome'}")
    print("─" * 110)
    for n in sorted(by_iter):
        row = by_iter[n]
        action_task = row.get("extract_action", {})
        action = _parse_maybe((action_task.get("outputData", {}) or {}).get("result"))
        tool_name = action.get("tool", "?") if isinstance(action, dict) else "?"
        trades = (action.get("args") or {}).get("trades") if isinstance(action, dict) else []
        trades_summary = (
            ", ".join(f"{t.get('action', '?')[0].upper()}{t.get('shares', '?')} {t.get('symbol', '?')}" for t in (trades or [])[:3])
            if trades
            else "—"
        )
        if trades and len(trades) > 3:
            trades_summary += f" +{len(trades) - 3}"

        result_task = row.get("extract_result", {})
        result = _parse_maybe((result_task.get("outputData", {}) or {}).get("result"))
        if not isinstance(result, dict):
            result = {}

        if tool_name == "submit_trades":
            outcome = "→ SUBMITTED"
        elif result.get("submitted"):
            outcome = "→ SUBMITTED"
        else:
            vcount = result.get("violation_count", 0)
            drift_ok = result.get("drift_within_tolerance")
            drift_bps = result.get("max_drift_bps")
            outcome = (
                f"{vcount} violation(s); drift={drift_bps} bps "
                f"{'(within tol)' if drift_ok else '(over tol)'}"
            )
        print(f"{n:>5}  {tool_name:<20}  {trades_summary:<40}  {outcome}")


def main(argv: list[str]) -> None:
    print(f"server: {BASE}")
    print(f"model:  {MODEL}\n")
    print(f"account: {PORTFOLIO['account_id']} ({PORTFOLIO['client']})")
    cw = _current_weights(PORTFOLIO)
    tv = _portfolio_value(PORTFOLIO["current_holdings"])
    print(f"value:   ${tv:,.0f}")
    print("weights: {")
    for ac, w in cw.items():
        target = PORTFOLIO["target_weights"].get(ac, 0.0)
        drift = (w - target) * 10000
        print(f"           {ac:<20}: {w * 100:5.1f}% (target {target * 100:.0f}%, drift {drift:+.0f} bps)")
    print("         }")
    print(f"restrictions: {PORTFOLIO['restrictions']}")
    print(f"budget:  {MAX_ITER} iterations\n")

    harness = plan_execute(
        name="portfolio_tools_harness",
        tools=TOOLS_LIST,
        planner_instructions="(unused — workflow def is hand-built)",
        model=MODEL,
    )

    from conductor.ai.agents.config_serializer import AgentConfigSerializer

    ac = AgentConfigSerializer().serialize(harness)
    tool_defs = ac.get("tools", [])

    with AgentRuntime() as runtime:
        runtime.serve(harness, blocking=False)
        print(f"workers serving: {[t.__name__ for t in TOOLS_LIST]}\n")

        wf_def = build_workflow_def(tool_defs)
        print("registering workflow def...")
        register_workflow(wf_def)
        print(f"  OK: {WORKFLOW_NAME} v{WORKFLOW_VERSION}\n")

        print("starting rebalancing...")
        execution_id = start_execution(PORTFOLIO)
        print(f"  execution_id: {execution_id}\n")

        print("polling until done...")
        wf = poll_until_done(execution_id)
        print(f"  status: {wf['status']}\n")

    output = wf.get("output", {}) or {}
    final = _parse_maybe(output.get("final_state"))

    print("── rebalancing trace (one row per iteration) ──")
    print_rebalance_trace(wf)
    print()

    print("── final ─────────────────────────────────────────────")
    print(f"  iterations: {output.get('iterations')}")
    print(f"  submitted:  {final.get('submitted')}")
    if final.get("submitted"):
        trades = final.get("trades") or []
        print(f"  trades ({len(trades)}):")
        for t in trades:
            print(f"    - {t.get('action', '?').upper():<4} {t.get('shares', '?')} {t.get('symbol', '?')}")
        if final.get("rationale"):
            print()
            print(f"  rationale: {final['rationale']}")
    else:
        print(f"  remaining violations: {final.get('violation_count', '?')}")
    print()
    print(f"inspect: curl {BASE}/api/workflow/{execution_id}?includeTasks=true | jq .")


if __name__ == "__main__":
    main(sys.argv)
