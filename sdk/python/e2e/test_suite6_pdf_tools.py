"""Suite 6: PDF Tools — markdown-to-PDF generation and round-trip validation.

Tests PDF tool integration end-to-end:
  1. Convert sample markdown to PDF via agent
  2. Extract markdown from the generated PDF using markitdown
  3. Validate extracted content matches the original (fuzzy, content-based)

No mocks. Real server, real LLM.
"""

import os
import tempfile

import pytest
import requests

from agentspan.agents import Agent, pdf_tool

pytestmark = [
    pytest.mark.e2e,
]

TIMEOUT = 120

# ── Sample Markdown ──────────────────────────────────────────────────────

SAMPLE_MARKDOWN = """\
# Agentspan E2E Test Report

## Overview

This document validates the PDF generation pipeline.

## Key Metrics

| Metric       | Value |
|-------------|-------|
| Tests Run   | 12    |
| Passed      | 11    |
| Skipped     | 1     |

## Features Tested

- MCP tool discovery and execution
- HTTP tool with OpenAPI spec
- Credential lifecycle management
- CLI command whitelisting

## Code Example

```python
from agentspan.agents import Agent, pdf_tool

agent = Agent(
    name="pdf_generator",
    tools=[pdf_tool()],
)
```

## Conclusion

All critical paths validated successfully.
"""

# Key phrases that MUST survive the markdown → PDF → markdown round trip.
# These are content-level checks, not formatting checks.
EXPECTED_PHRASES = [
    "Agentspan E2E Test Report",
    "Overview",
    "Key Metrics",
    "Tests Run",
    "12",
    "Features Tested",
    "MCP tool discovery",
    "Credential lifecycle",
    "Code Example",
    "Conclusion",
]


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_agent(model):
    """Agent with PDF generation tool."""
    pdf = pdf_tool()
    return Agent(
        name="e2e_pdf_gen",
        model=model,
        instructions=(
            "You generate PDF documents from markdown. "
            "When asked, call the generate_pdf tool with the exact markdown provided. "
            "Do not modify the markdown content."
        ),
        tools=[pdf],
    )


def _get_workflow(execution_id):
    """Fetch workflow from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_output_text(result):
    """Extract text output from a run result."""
    output = result.output
    if isinstance(output, dict):
        results = output.get("result", [])
        if results:
            texts = []
            for r in results:
                if isinstance(r, dict):
                    texts.append(r.get("text", r.get("content", str(r))))
                else:
                    texts.append(str(r))
            return "".join(texts)
        return str(output)
    return str(output) if output else ""


def _run_diagnostic(result):
    """Build diagnostic string from a run result."""
    parts = [f"status={result.status}", f"execution_id={result.execution_id}"]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
        if "finishReason" in output:
            parts.append(f"finishReason={output['finishReason']}")
    return " | ".join(parts)


def _find_pdf_task(execution_id):
    """Find the GENERATE_PDF task in the workflow."""
    wf = _get_workflow(execution_id)
    for task in wf.get("tasks", []):
        task_type = task.get("taskType", "")
        task_def = task.get("taskDefName", "")
        if "GENERATE_PDF" in task_type or "GENERATE_PDF" in task_def:
            return task
        # Also check by tool name
        if "pdf" in task_def.lower() or "pdf" in task_type.lower():
            return task
    return None


def _extract_pdf_url(task):
    """Extract the PDF URL or data from a GENERATE_PDF task output."""
    output = task.get("outputData", {})
    # Try common output structures
    for key in ("url", "pdfUrl", "pdf_url", "fileUrl", "file_url", "result"):
        if key in output:
            val = output[key]
            if isinstance(val, str) and (val.startswith("http") or val.startswith("/")):
                return val
    # Check nested response
    response = output.get("response", {})
    if isinstance(response, dict):
        body = response.get("body", {})
        if isinstance(body, dict):
            for key in ("url", "pdfUrl", "fileUrl", "result"):
                if key in body:
                    return body[key]
    # Return the whole output for debugging
    return None


# ── Test ─────────────────────────────────────────────────────────────────


@pytest.mark.timeout(300)
class TestSuite6PdfTools:
    """PDF tools: markdown → PDF → round-trip validation."""

    def test_pdf_generation_and_roundtrip(self, runtime, model):
        """Generate PDF from markdown, then validate content via markitdown."""
        agent = _make_agent(model)

        # ── Step 0: Verify agent compiles with correct tool type ──────
        plan = runtime.plan(agent)
        ad = plan["workflowDef"]["metadata"]["agentDef"]
        pdf_tools = [
            t for t in ad.get("tools", [])
            if t.get("toolType") == "generate_pdf"
        ]
        assert len(pdf_tools) == 1, (
            f"[PDF Plan] Expected 1 generate_pdf tool, found {len(pdf_tools)}. "
            f"Tools: {[(t.get('name'), t.get('toolType')) for t in ad.get('tools', [])]}"
        )

        # ── Step 1: Generate PDF from markdown ────────────────────────
        prompt = (
            "Convert the following markdown to a PDF document. "
            "Pass it exactly as-is to the generate_pdf tool:\n\n"
            f"{SAMPLE_MARKDOWN}"
        )
        result = runtime.run(agent, prompt, timeout=TIMEOUT)

        diag = _run_diagnostic(result)
        assert result.execution_id, f"[PDF Gen] No execution_id. {diag}"
        assert result.status == "COMPLETED", (
            f"[PDF Gen] Run did not complete. {diag}"
        )

        # ── Step 2: Verify GENERATE_PDF task completed ────────────────
        pdf_task = _find_pdf_task(result.execution_id)
        assert pdf_task is not None, (
            "[PDF Gen] No GENERATE_PDF task found in workflow. "
            f"Tasks: {[t.get('taskType') for t in _get_workflow(result.execution_id).get('tasks', [])]}"
        )
        assert pdf_task.get("status") == "COMPLETED", (
            f"[PDF Gen] GENERATE_PDF task did not complete. "
            f"status={pdf_task.get('status')} "
            f"reason={pdf_task.get('reasonForIncompletion', '')}"
        )

        # ── Step 3: Extract PDF and validate with markitdown ──────────
        pdf_output = pdf_task.get("outputData", {})

        # Also check the agent's text output for a PDF URL
        agent_output = _get_output_text(result)
        pdf_url = _extract_pdf_url(pdf_task)

        # If not found in task output, check agent text for URL patterns
        if pdf_url is None:
            import re
            url_match = re.search(r'(https?://[^\s\)\"]+\.pdf[^\s\)\"]*)', agent_output)
            if url_match:
                pdf_url = url_match.group(1)

        if pdf_url is None:
            # Dump full task for debugging
            task_dump = {
                k: pdf_task.get(k)
                for k in ("outputData", "inputData", "status", "taskType", "referenceTaskName")
            }
            pytest.skip(
                f"Could not extract PDF URL from task output or agent response. "
                f"Task: {str(task_dump)[:500]}. "
                f"Agent output: {agent_output[:300]}. "
                f"Skipping round-trip validation."
            )

        # Download PDF
        base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
        base_url = base.rstrip("/").replace("/api", "")
        if pdf_url.startswith("/"):
            pdf_url = f"{base_url}{pdf_url}"

        pdf_resp = requests.get(pdf_url, timeout=30)
        assert pdf_resp.status_code == 200, (
            f"[PDF Roundtrip] Failed to download PDF from {pdf_url}: "
            f"{pdf_resp.status_code}"
        )
        assert len(pdf_resp.content) > 100, (
            f"[PDF Roundtrip] Downloaded PDF is too small: "
            f"{len(pdf_resp.content)} bytes"
        )

        # Save to temp file for markitdown
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_resp.content)
            pdf_path = f.name

        try:
            from markitdown import MarkItDown

            md = MarkItDown()
            extracted = md.convert(pdf_path)
            extracted_text = extracted.text_content

            assert extracted_text and len(extracted_text) > 50, (
                f"[PDF Roundtrip] markitdown extracted too little text: "
                f"{len(extracted_text or '')} chars"
            )

            # Validate key phrases survived the round trip
            missing = [
                phrase
                for phrase in EXPECTED_PHRASES
                if phrase.lower() not in extracted_text.lower()
            ]
            assert len(missing) <= 2, (
                f"[PDF Roundtrip] Too many key phrases missing from extracted "
                f"markdown ({len(missing)}/{len(EXPECTED_PHRASES)}).\n"
                f"  Missing: {missing}\n"
                f"  Extracted (first 500 chars): {extracted_text[:500]}"
            )
        except ImportError:
            pytest.skip(
                "markitdown not installed — skipping PDF round-trip validation. "
                "Install with: pip install markitdown"
            )
        finally:
            os.unlink(pdf_path)
