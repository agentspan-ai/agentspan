"""Record every tool call of a triage, and replay a triage from that recording.

Record (``ONCALL_RECORD_DIR``): each tool call is appended to
``<dir>/<execution_id>.jsonl`` as ``{tool, args, result | error, ms}``. That file is
the full evidence trail of a triage: what the agent asked, what it saw.

Replay (``ONCALL_REPLAY_DIR``): tools return what was recorded for the same tool and
arguments instead of touching any cluster, cloud or database. An eval case then
costs only the LLM, gives the same evidence every run, and still works after the
cluster has moved on. A call that was never recorded returns ``not_recorded`` with
the recorded alternatives, so the agent can pick one instead of guessing.
"""
from __future__ import annotations

import functools
import json
import os
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

_lock = threading.Lock()
_replay: dict[str, dict[str, list[dict]]] = {}  # execution_id -> call key -> recorded calls
_served: dict[str, int] = defaultdict(int)


def _key(tool: str, args: dict) -> str:
    return tool + json.dumps(args, sort_keys=True, default=str)


def _record(tool: str, args: dict, entry: dict) -> None:
    out = Path(os.environ["ONCALL_RECORD_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"tool": tool, "args": args, **entry}, default=str)
    with _lock, open(out / f"{args.get('execution_id', '_')}.jsonl", "a") as f:
        f.write(line + "\n")


def _load(execution_id: str) -> dict[str, list[dict]]:
    if execution_id not in _replay:
        calls: dict[str, list[dict]] = defaultdict(list)
        path = Path(os.environ["ONCALL_REPLAY_DIR"]) / f"{execution_id}.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    c = json.loads(line)
                    calls[_key(c["tool"], c["args"])].append(c)
        _replay[execution_id] = calls
    return _replay[execution_id]


def _play(tool: str, args: dict) -> Any:
    calls = _load(str(args.get("execution_id", "_")))
    key = _key(tool, args)
    with _lock:
        recorded = calls.get(key)
        if not recorded:
            # Logged so the eval can say how much of a replayed triage ran on missing evidence.
            with open(Path(os.environ["ONCALL_REPLAY_DIR"]) / "_misses.jsonl", "a") as f:
                f.write(json.dumps({"execution_id": args.get("execution_id"), "tool": tool, "args": args},
                                   default=str) + "\n")
            options = [c["args"] for k, cs in calls.items() for c in cs[:1] if c["tool"] == tool]
            return {"error": "not_recorded",
                    "detail": f"{tool} was not called with these arguments when this incident was "
                              f"recorded; recorded calls: {options[:10] or 'none'}"}
        # Repeated identical calls get the recorded answers in order, then the last one again.
        i = min(_served[key], len(recorded) - 1)
        _served[key] += 1
    call = recorded[i]
    if "error" in call and "result" not in call:
        raise RuntimeError(call["error"])
    return call["result"]


def wrap(tool: str, fn: Callable) -> Callable:
    """Record or replay ``fn`` per the environment; a plain pass-through otherwise."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Tools are invoked with keyword arguments by the worker; positional ones are named here.
        names = list(fn.__code__.co_varnames[: fn.__code__.co_argcount])
        call_args = {**dict(zip(names, args)), **kwargs}
        if os.environ.get("ONCALL_REPLAY_DIR"):
            return _play(tool, call_args)
        if not os.environ.get("ONCALL_RECORD_DIR"):
            return fn(*args, **kwargs)
        started = time.time()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            _record(tool, call_args, {"error": f"{type(exc).__name__}: {exc}",
                                      "ms": int((time.time() - started) * 1000)})
            raise
        _record(tool, call_args, {"result": result, "ms": int((time.time() - started) * 1000)})
        return result

    return wrapper
