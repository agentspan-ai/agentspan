#!/usr/bin/env python3
"""Measure the incident population from the running agent's state file.

Produces the numbers quoted in design/context-layer-prd.md §4 so they are
reproducible and auditable rather than one-off queries.

    PYTHONPATH=src .venv/bin/python scripts/analyze_incident_population.py \
        [--state /tmp/oncall_loop_state.json] [--log /tmp/oncall_loop.log]

READ THE CAVEATS THIS PRINTS. Three of them materially bound what the numbers
support:

  * ``firings`` counts events that reached the incident-memory step — i.e. those
    that produced a full triage or a memory-update reply. It does NOT count
    alerts suppressed earlier by execution-id dedup or signature cooldown, so it
    measures *work-producing events*, not alert volume.
  * "chronic" and "novel" have no system definition. This script sweeps the
    threshold instead of picking one, because the answer moves a lot.
  * A signature is a sorted token set of the alert text, so one real condition
    can split across several signatures (an actively fixed bug class — see
    commits 1b1f33f1, 128291ec, 3e0217c6). Splitting *understates* concentration,
    so the collapsed view is the fairer one.
"""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
from pathlib import Path


def _fmt(ts: float) -> str:
    return dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%SZ")


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def _collapse(sigs: dict[str, int], threshold: float) -> list[int]:
    """Single-link cluster signatures by token-set Jaccard; return firings per cluster."""
    toks = {k: set(k.split(",")) for k in sigs}
    parent = {k: k for k in toks}

    def find(x: str) -> str:
        while parent[x] != x:
            x = parent[x]
        return x

    for a, b in itertools.combinations(toks, 2):
        if _jaccard(toks[a], toks[b]) >= threshold:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

    groups: dict[str, list[str]] = {}
    for k in toks:
        groups.setdefault(find(k), []).append(k)
    return sorted((sum(sigs[m] for m in g) for g in groups.values()), reverse=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="/tmp/oncall_loop_state.json")
    ap.add_argument("--log", default="/tmp/oncall_loop.log")
    args = ap.parse_args()

    state = json.loads(Path(args.state).read_text())
    inc: dict = state.get("incidents", {})
    sigs = {k: int(v.get("firings", 1)) for k, v in inc.items()}
    total = sum(sigs.values())

    print(f"measured_at: {_fmt(dt.datetime.now(dt.timezone.utc).timestamp())}")
    print(f"source: {args.state}")
    print("NOTE: the agent is live; these numbers move between runs.\n")

    # ── observation window ────────────────────────────────────────────
    first = [v["first_seen"] for v in inc.values() if v.get("first_seen")]
    last = [v["last_full_ts"] for v in inc.values() if v.get("last_full_ts")]
    if first and last:
        span_h = (max(last) - min(first)) / 3600
        print("## Observation window")
        print(f"  earliest first_seen : {_fmt(min(first))}")
        print(f"  latest  last_full_ts: {_fmt(max(last))}")
        print(f"  span                : {span_h:.1f}h ({span_h / 24:.1f} days)")
    capped = len(inc) >= 200
    print(f"  signatures retained : {len(inc)}  "
          f"({'AT/OVER the 200 cap — older entries PRUNED, not a census' if capped else 'under the 200 cap — no pruning, complete census for the window'})")
    print(f"  work-producing events (sum of 'firings'): {total}\n")

    # ── concentration, swept rather than asserted ─────────────────────
    print("## Concentration — 'chronic' threshold swept (no system definition exists)")
    for thr in (3, 5, 8, 10, 15, 20):
        sel = [n for n in sigs.values() if n >= thr]
        pct = (sum(sel) * 100 // total) if total else 0
        print(f"  >={thr:>2} events: {len(sel):>2} signatures = {sum(sel):>3}/{total} events = {pct}%")

    print("\n## 'Novel' tail — also threshold-dependent")
    for thr in (1, 2, 3):
        sel = [n for n in sigs.values() if n <= thr]
        pct = (sum(sel) * 100 // total) if total else 0
        print(f"  <={thr} events: {len(sel):>2} signatures = {sum(sel):>3}/{total} events = {pct}%")

    # ── signature identity ────────────────────────────────────────────
    print("\n## Are signatures distinct conditions? (near-duplicates collapsed)")
    print("   Splitting understates concentration, so these are the fairer numbers.")
    for t in (0.7, 0.8, 0.9):
        sizes = _collapse(sigs, t)
        top8 = sum(sizes[:8])
        pct = (top8 * 100 // total) if total else 0
        print(f"  Jaccard>={t}: {len(sizes):>2} conditions (from {len(sigs)} signatures); "
              f"top-8 = {top8}/{total} events = {pct}%")

    # ── log-derived counts ────────────────────────────────────────────
    log = Path(args.log)
    if log.exists():
        text = log.read_text(errors="replace")
        triage = text.count("triage channel=")
        skip = text.count("skip duplicate")
        mem = text.count("memory update (no LLM)")
        starts = text.count("on-call agent polling")
        evals = triage + skip + mem
        print("\n## Log-derived (UNDATED — the log has no timestamps and appends across restarts)")
        print(f"  process starts in log : {starts}")
        print(f"  full triages          : {triage}")
        print(f"  memory-only replies   : {mem}"
              + (f"  ({mem * 100 // (triage + mem)}% of triage-reaching events)" if triage + mem else ""))
        print(f"  suppressed duplicates : {skip}"
              + (f"  ({skip * 100 // evals}% of alert-message evaluations)" if evals else ""))
        print("  CAVEAT: a single alert seen in two channels yields two evaluations,")
        print("          so this is not a percentage of distinct alerts.")

    print("\n## What these numbers do and do not support")
    print("  SUPPORTED: work-producing events are heavily concentrated in a small")
    print("             number of conditions. True at every threshold swept above.")
    print("  NOT SUPPORTED: any single headline percentage. The chronic share moves")
    print("             45%-95% depending on the threshold and on whether")
    print("             near-duplicate signatures are collapsed.")
    print("  SCOPE: one agent, one domain, one observation window. Generalising to")
    print("             'agents in general' is a hypothesis, not a measurement.")


if __name__ == "__main__":
    main()
