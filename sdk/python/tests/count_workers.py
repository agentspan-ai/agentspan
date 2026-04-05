"""
Count workers for all LangGraph examples by running each in a subprocess.
Usage: cd sdk/python && uv run python tests/count_workers.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sdk_root = Path(__file__).parent.parent
examples_dir = sdk_root / "examples" / "langgraph"
harness = sdk_root / "tests" / "_worker_harness.py"

files = sorted(f for f in os.listdir(examples_dir) if f.endswith(".py") and f[0].isdigit())

results = []

for fname in files:
    num = fname.split("_")[0]
    fpath = examples_dir / fname

    try:
        proc = subprocess.run(
            ["uv", "run", "python", str(harness), str(fpath)],
            cwd=str(sdk_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        stdout = proc.stdout.strip()
        lines = [l for l in stdout.split("\n") if l.strip()]
        if lines:
            data = json.loads(lines[-1])
            results.append({"example": num, **data})
        else:
            stderr = proc.stderr[:100] if proc.stderr else "no output"
            results.append({"example": num, "workers": -1, "hasGraph": False, "error": stderr})
    except subprocess.TimeoutExpired:
        results.append({"example": num, "workers": -1, "hasGraph": False, "error": "timeout"})
    except Exception as e:
        results.append({"example": num, "workers": -1, "hasGraph": False, "error": str(e)[:80]})

print(json.dumps(results, indent=2))
