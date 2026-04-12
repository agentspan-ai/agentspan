"""Generate a self-contained HTML report from pytest junit XML output."""

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


def generate_report(junit_xml_path: str, output_path: str) -> None:
    """Parse junit XML and produce a single-file HTML report."""
    tree = ET.parse(junit_xml_path)
    root = tree.getroot()

    # Collect suites — handle both <testsuites> wrapper and bare <testsuite>
    if root.tag == "testsuites":
        suites = list(root)
    else:
        suites = [root]

    total = passed = failed = skipped = errors = 0
    total_time = 0.0
    # Group tests by suite file, not by pytest's flat grouping
    suite_map: dict[str, list[dict]] = {}

    for suite in suites:
        for tc in suite.findall("testcase"):
            name = tc.get("name", "unknown")
            classname = tc.get("classname", "")
            time_s = float(tc.get("time", "0"))
            total_time += time_s
            total += 1

            failure = tc.find("failure")
            error = tc.find("error")
            skip = tc.find("skipped")

            if failure is not None:
                status = "FAILED"
                detail = failure.text or failure.get("message", "")
                message = failure.get("message", "")
                failed += 1
            elif error is not None:
                status = "ERROR"
                detail = error.text or error.get("message", "")
                message = error.get("message", "")
                errors += 1
            elif skip is not None:
                status = "SKIPPED"
                detail = skip.get("message", "")
                message = detail
                skipped += 1
            else:
                status = "PASSED"
                detail = ""
                message = ""
                passed += 1

            # Extract a human-readable error summary from the detail
            error_summary = _extract_error_summary(message, detail)
            # Extract file:line from the traceback
            location = _extract_location(detail)

            suite_key = _suite_key_from_classname(classname)
            suite_map.setdefault(suite_key, []).append(
                {
                    "name": name,
                    "classname": classname,
                    "time": time_s,
                    "status": status,
                    "detail": detail,
                    "error_summary": error_summary,
                    "location": location,
                }
            )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    suite_data = [
        {"name": key, "tests": tests} for key, tests in suite_map.items()
    ]

    html = _render_html(
        timestamp, total_time, total, passed, failed, skipped, errors, suite_data
    )
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Report written to {output_path}")


def _suite_key_from_classname(classname: str) -> str:
    """Derive a readable suite name from the pytest classname.

    e.g. 'e2e.test_suite1_basic_validation.TestSuite1BasicValidation'
      -> 'Suite 1: Basic Validation'
    e.g. 'e2e.test_suite2_tool_calling.TestSuite2ToolCalling'
      -> 'Suite 2: Tool Calling'
    Falls back to the module portion of classname.
    """
    # Find the test_suite* module in the dotted classname
    parts = classname.split(".")
    module = ""
    for part in parts:
        if part.startswith("test_suite"):
            module = part
            break

    if not module:
        # Fall back: use the second-to-last part (module name), or first
        module = parts[-2] if len(parts) >= 2 else parts[0]

    # Try to parse suite number and name from module
    m = re.match(r"test_suite(\d+)_(.+)", module)
    if m:
        num = m.group(1)
        words = m.group(2).replace("_", " ").title()
        return f"Suite {num}: {words}"

    return module or "Tests"


def _extract_error_summary(message: str, detail: str) -> str:
    """Extract a clean, one-line error summary from pytest output.

    Looks for AssertionError message first, then falls back to the
    failure message attribute.
    """
    # Look for "AssertionError: <message>" in the detail
    for line in detail.splitlines():
        line = line.strip()
        if line.startswith("AssertionError:"):
            return line[len("AssertionError:"):].strip()
        if line.startswith("E   AssertionError:"):
            return line[len("E   AssertionError:"):].strip()

    # Fall back to the message attribute (often has the assertion text)
    if message:
        # Strip "AssertionError:" prefix if present
        if message.startswith("AssertionError:"):
            return message[len("AssertionError:"):].strip()
        return message.split("\n")[0].strip()

    return ""


def _extract_location(detail: str) -> str:
    """Extract 'file:line' from pytest traceback.

    Looks for lines like 'e2e/test_suite2_tool_calling.py:174: in _run_lifecycle'
    and returns the last one (closest to the assertion).
    """
    locations = []
    for line in detail.splitlines():
        m = re.match(r"(\S+\.py):(\d+):", line.strip())
        if m:
            locations.append(f"{m.group(1)}:{m.group(2)}")
    return locations[-1] if locations else ""


def _render_html(
    timestamp, total_time, total, passed, failed, skipped, errors, suites
):
    status_colors = {
        "PASSED": "#22c55e",
        "FAILED": "#ef4444",
        "ERROR": "#f97316",
        "SKIPPED": "#eab308",
    }

    test_rows = []
    for suite in suites:
        suite_id = re.sub(r"[^a-zA-Z0-9]", "_", suite["name"])
        suite_pass = sum(1 for t in suite["tests"] if t["status"] == "PASSED")
        suite_fail = sum(
            1 for t in suite["tests"] if t["status"] in ("FAILED", "ERROR")
        )
        suite_total = len(suite["tests"])
        suite_status_color = "#22c55e" if suite_fail == 0 else "#ef4444"
        suite_label = (
            f"{suite_pass}/{suite_total} passed"
            if suite_fail == 0
            else f"{suite_fail} failed, {suite_pass} passed"
        )
        test_rows.append(
            f"<tr class='suite-header' onclick=\"toggleSuite('{suite_id}')\">"
            f"<td colspan='3'>{_esc(suite['name'])}</td>"
            f"<td style='color:{suite_status_color}'>{suite_label}</td>"
            f"</tr>"
        )
        for t in suite["tests"]:
            color = status_colors.get(t["status"], "#888")

            # Build the detail cell content
            detail_parts = []

            # For failures/errors: show error summary prominently
            if t["status"] in ("FAILED", "ERROR") and t["error_summary"]:
                detail_parts.append(
                    f"<div class='error-summary'>{_esc(t['error_summary'])}</div>"
                )

            # Show file:line for failures
            if t["location"]:
                detail_parts.append(
                    f"<div class='error-location'>{_esc(t['location'])}</div>"
                )

            # Full traceback in collapsible section
            if t["detail"]:
                detail_parts.append(
                    f"<details><summary>Full traceback</summary>"
                    f"<pre>{_esc(t['detail'])}</pre></details>"
                )

            # For skipped tests, show the skip reason
            if t["status"] == "SKIPPED" and t["error_summary"]:
                detail_parts.append(
                    f"<span class='skip-reason'>{_esc(t['error_summary'])}</span>"
                )

            detail_html = "\n".join(detail_parts)

            row_class = "suite-row " + suite_id
            if t["status"] in ("FAILED", "ERROR"):
                row_class += " failed-row"

            test_rows.append(
                f"<tr class='{row_class}'>"
                f"<td>{_esc(t['name'])}</td>"
                f"<td style='color:{color};font-weight:bold'>{t['status']}</td>"
                f"<td>{t['time']:.2f}s</td>"
                f"<td>{detail_html}</td>"
                f"</tr>"
            )

    rows_html = "\n".join(test_rows)
    overall = "PASSED" if failed == 0 and errors == 0 else "FAILED"
    overall_color = "#22c55e" if overall == "PASSED" else "#ef4444"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>E2E Test Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
         background: #0f172a; color: #e2e8f0; padding: 2rem; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
  .summary {{ display: flex; gap: 1.5rem; margin-bottom: 1.5rem; flex-wrap: wrap; }}
  .stat {{ background: #1e293b; padding: 1rem 1.5rem; border-radius: 8px; }}
  .stat .label {{ font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; }}
  .stat .value {{ font-size: 1.5rem; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; padding: 0.5rem 1rem; background: #1e293b; color: #94a3b8;
       font-size: 0.75rem; text-transform: uppercase; }}
  td {{ padding: 0.5rem 1rem; border-bottom: 1px solid #1e293b; vertical-align: top; }}
  tr.suite-header {{ cursor: pointer; }}
  tr.suite-header td {{ background: #1e293b; font-weight: bold; color: #60a5fa;
                        padding: 0.75rem 1rem; }}
  tr.suite-header:hover td {{ background: #334155; }}
  tr.failed-row td {{ background: #1c1117; }}
  .error-summary {{ color: #fca5a5; font-weight: 600; margin-bottom: 0.25rem;
                     line-height: 1.4; }}
  .error-location {{ color: #94a3b8; font-size: 0.8rem; margin-bottom: 0.25rem; }}
  .skip-reason {{ color: #eab308; font-size: 0.85rem; }}
  details {{ margin-top: 0.5rem; }}
  summary {{ cursor: pointer; color: #64748b; font-size: 0.8rem; }}
  summary:hover {{ color: #94a3b8; }}
  pre {{ background: #1e293b; padding: 1rem; border-radius: 4px; overflow-x: auto;
         font-size: 0.75rem; margin-top: 0.5rem; white-space: pre-wrap;
         max-height: 400px; overflow-y: auto; }}
</style>
<script>
function toggleSuite(suiteId) {{
  document.querySelectorAll('.suite-row.' + suiteId).forEach(function(row) {{
    row.style.display = row.style.display === 'none' ? '' : 'none';
  }});
}}
</script>
</head>
<body>
<h1>E2E Test Report</h1>
<div class="summary">
  <div class="stat">
    <div class="label">Status</div>
    <div class="value" style="color:{overall_color}">{overall}</div>
  </div>
  <div class="stat">
    <div class="label">Total</div>
    <div class="value">{total}</div>
  </div>
  <div class="stat">
    <div class="label">Passed</div>
    <div class="value" style="color:#22c55e">{passed}</div>
  </div>
  <div class="stat">
    <div class="label">Failed</div>
    <div class="value" style="color:#ef4444">{failed}</div>
  </div>
  <div class="stat">
    <div class="label">Skipped</div>
    <div class="value" style="color:#eab308">{skipped}</div>
  </div>
  <div class="stat">
    <div class="label">Duration</div>
    <div class="value">{total_time:.1f}s</div>
  </div>
  <div class="stat">
    <div class="label">Timestamp</div>
    <div class="value" style="font-size:1rem">{timestamp}</div>
  </div>
</div>
<table>
<thead><tr><th>Test</th><th>Status</th><th>Time</th><th>Detail</th></tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python report_generator.py <junit.xml> <output.html>")
        sys.exit(1)
    generate_report(sys.argv[1], sys.argv[2])
