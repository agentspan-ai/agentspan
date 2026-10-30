"""LLM usage of one agent execution: what an investigation costs.

Every LLM call of an Agentspan execution records its prompt and completion tokens; summed,
they are the incident's cost. Dollars are shown only when prices are configured
(ONCALL_USD_PER_MTOK_IN / ONCALL_USD_PER_MTOK_OUT, per million tokens) — never guessed.
"""
from __future__ import annotations

import os

import requests


def tokens(server: str, execution_id: str | None) -> dict:
    """{"llm_calls", "tokens_in", "tokens_out"} summed over the execution's LLM calls."""
    out = {"llm_calls": 0, "tokens_in": 0, "tokens_out": 0}
    if not execution_id:
        return out
    try:
        wf = requests.get(f"{server.rstrip('/')}/workflow/{execution_id}",
                          params={"includeTasks": "true"}, timeout=30).json()
    except Exception:
        return out
    for t in wf.get("tasks", []):
        if t.get("taskType") == "LLM_CHAT_COMPLETE":
            o = t.get("outputData") or {}
            out["llm_calls"] += 1
            out["tokens_in"] += int(o.get("promptTokens") or 0)
            out["tokens_out"] += int(o.get("completionTokens") or 0)
    return out


def usd(tokens_in: int, tokens_out: int) -> float | None:
    p_in, p_out = os.environ.get("ONCALL_USD_PER_MTOK_IN"), os.environ.get("ONCALL_USD_PER_MTOK_OUT")
    if not p_in or not p_out:
        return None
    return round(tokens_in / 1e6 * float(p_in) + tokens_out / 1e6 * float(p_out), 4)
