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


def _join_adjacent_strings(source: str, pos: int) -> str:
    """Starting at pos in source, collect and join adjacent string literals."""
    parts = []
    i = pos
    while i < len(source):
        # Skip whitespace and newlines between adjacent strings
        while i < len(source) and source[i] in " \t\n\r":
            i += 1
        if i >= len(source):
            break
        quote = source[i]
        if quote not in ('"', "'"):
            break
        # Find matching closing quote (non-escaped)
        j = i + 1
        while j < len(source):
            if source[j] == "\\" :
                j += 2
                continue
            if source[j] == quote:
                parts.append(source[i + 1:j])
                i = j + 1
                break
            j += 1
        else:
            break
    return "".join(parts)


def extract_prompt(example_name: str) -> str:
    example_file = EXAMPLES_DIR / f"{example_name}.py"
    if not example_file.exists():
        return "unknown prompt"
    source = example_file.read_text()

    # Inline string literal (possibly multi-line concatenation): run(agent, "..." "...")
    m = re.search(r'(?:run|stream)\s*\(\s*\w+\s*,\s*(["\'])', source)
    if m:
        prompt = _join_adjacent_strings(source, m.start(1))
        if prompt:
            return prompt

    # Variable: run(agent, var_name) — look up var_name = "..." assignment
    m = re.search(r'(?:run|stream)\s*\(\s*\w+\s*,\s*(\w+)', source)
    if m:
        var_name = m.group(1)
        m2 = re.search(rf'{var_name}\s*=\s*(["\'])', source)
        if m2:
            prompt = _join_adjacent_strings(source, m2.start(1))
            if prompt:
                return prompt

    return "unknown prompt"
