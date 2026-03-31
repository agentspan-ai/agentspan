"""Output parsing, prompt extraction, and raw output loading."""

from __future__ import annotations

import re

from .config import EXAMPLES_DIR
from .models import RunResult

# Shared regex for extracting agent output from stdout
AGENT_OUTPUT_RE = re.compile(
    r"╘═+╛\s*\n(.*?)(?=\nTool calls:|\nTokens:|\nFinish reason:|\nExecution ID:|\n\n\n|\Z)",
    re.DOTALL,
)


def parse_output(
    stdout: str, stderr: str, exit_code: int, duration: float, timed_out: bool
) -> RunResult:
    r = RunResult(exit_code=exit_code, duration_s=round(duration, 1))

    if timed_out:
        r.status = "TIMEOUT"
        r.has_error = True
        r.error_summary = f"Timed out after {duration:.0f}s"
        r.stdout = stdout
        r.stderr = stderr
        return r

    # Execution ID
    m = re.search(r"Execution ID: (\S+)", stdout)
    if m:
        r.execution_id = m.group(1)

    # Tool calls
    m = re.search(r"Tool calls: (\d+)", stdout)
    if m:
        r.tool_calls = int(m.group(1))

    # Tokens
    m = re.search(r"Tokens: (\d+) total \((\d+) prompt, (\d+) completion\)", stdout)
    if m:
        r.tokens_total = int(m.group(1))
        r.tokens_prompt = int(m.group(2))
        r.tokens_completion = int(m.group(3))

    # Agent output
    output_match = AGENT_OUTPUT_RE.search(stdout)
    if output_match:
        r.output_text = output_match.group(1).strip()
        r.output_length = len(r.output_text)

    # Errors
    combined = stdout + "\n" + stderr
    has_traceback = "Traceback" in combined
    has_workflow_failed = "workflow FAILED" in combined
    has_error_in_stderr = stderr.strip() != "" and any(
        kw in stderr for kw in ("Error", "Exception", "Traceback", "FAILED")
    )
    r.has_error = has_traceback or has_workflow_failed or has_error_in_stderr or exit_code != 0

    if r.has_error:
        for text in [stderr, stdout]:
            for line in text.splitlines():
                if any(kw in line for kw in ["Error:", "Exception:", "FAILED"]):
                    r.error_summary = line.strip()[:200]
                    break
            if r.error_summary:
                break

    # Status
    if has_workflow_failed:
        r.status = "FAILED"
    elif exit_code == 0 and not r.has_error:
        r.status = "COMPLETED"
    elif timed_out:
        r.status = "TIMEOUT"
    elif exit_code != 0:
        r.status = "FAILED"
    else:
        r.status = "ERROR"

    r.stdout = stdout
    r.stderr = stderr
    return r


def extract_prompt(example_name: str) -> str:
    example_file = EXAMPLES_DIR / f"{example_name}.py"
    if not example_file.exists():
        return "unknown prompt"
    source = example_file.read_text()
    m = re.search(r'(?:run|stream)\s*\(\s*\w+\s*,\s*"([^"]+)"', source)
    if m:
        return m.group(1)
    m = re.search(r"(?:run|stream)\s*\(\s*\w+\s*,\s*'([^']+)'", source)
    if m:
        return m.group(1)
    return "unknown prompt"
