"""Suite 7: Media Tools — image and audio generation.

Tests media generation tools end-to-end:
  - Image generation via OpenAI (dall-e-3) and Gemini (imagen-3.0)
  - Audio generation via OpenAI (tts-1)

Each test validates agent completion and output presence.
Skips if required API keys are not set.
No mocks. Real server, real LLM, real media generation APIs.
"""

import os

import pytest
import requests

from agentspan.agents import Agent, audio_tool, image_tool

pytestmark = [
    pytest.mark.e2e,
]

TIMEOUT = 180  # Media generation can be slow

# ── Helpers ──────────────────────────────────────────────────────────────


def _get_workflow(execution_id):
    """Fetch workflow from server API."""
    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _run_diagnostic(result):
    """Build diagnostic string from a run result."""
    parts = [f"status={result.status}", f"execution_id={result.execution_id}"]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
        if "finishReason" in output:
            parts.append(f"finishReason={output['finishReason']}")
    return " | ".join(parts)


def _find_media_task(execution_id, task_type_prefix):
    """Find a media generation task in the workflow.

    Searches for tasks whose taskType or taskDefName contains the prefix
    (e.g., 'GENERATE_IMAGE', 'GENERATE_AUDIO', 'GENERATE_VIDEO').
    """
    wf = _get_workflow(execution_id)
    for task in wf.get("tasks", []):
        tt = task.get("taskType", "")
        td = task.get("taskDefName", "")
        if task_type_prefix in tt or task_type_prefix in td:
            return task
    return None


def _assert_media_generated(result, step_name, task_type_prefix):
    """Validate agent completed and media task produced output."""
    diag = _run_diagnostic(result)

    assert result.execution_id, f"[{step_name}] No execution_id. {diag}"
    assert result.status == "COMPLETED", (
        f"[{step_name}] Run did not complete. {diag}"
    )

    media_task = _find_media_task(result.execution_id, task_type_prefix)
    assert media_task is not None, (
        f"[{step_name}] No {task_type_prefix} task found in workflow. "
        f"Tasks: {[t.get('taskType') for t in _get_workflow(result.execution_id).get('tasks', [])]}"
    )
    task_status = media_task.get("status", "")
    reason = media_task.get("reasonForIncompletion", "")

    assert task_status == "COMPLETED", (
        f"[{step_name}] {task_type_prefix} task did not complete. "
        f"status={task_status} reason={reason[:300]}"
    )

    output = media_task.get("outputData", {})
    assert output, (
        f"[{step_name}] {task_type_prefix} task has empty outputData."
    )

    return output


def _assert_tool_compiled(runtime, agent, expected_tool_type, expected_model, step_name):
    """Verify the agent's compiled plan has the correct tool type and model."""
    plan = runtime.plan(agent)
    ad = plan["workflowDef"]["metadata"]["agentDef"]
    tools = [t for t in ad.get("tools", []) if t.get("toolType") == expected_tool_type]
    assert len(tools) >= 1, (
        f"[{step_name}] No {expected_tool_type} tool in compiled agent. "
        f"Tools: {[(t.get('name'), t.get('toolType')) for t in ad.get('tools', [])]}"
    )
    config = tools[0].get("config", {})
    actual_model = config.get("model", "")
    assert actual_model == expected_model, (
        f"[{step_name}] Wrong model in compiled tool config. "
        f"expected={expected_model}, actual={actual_model}"
    )


# ── Test ─────────────────────────────────────────────────────────────────


@pytest.mark.timeout(600)
class TestSuite7MediaTools:
    """Media tools: image and audio generation."""

    # ── Image: OpenAI ─────────────────────────────────────────────────

    def test_image_openai(self, runtime, model):
        """Generate image via OpenAI DALL-E 3."""
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        img = image_tool(
            name="gen_image",
            description="Generate an image from a text prompt.",
            llm_provider="openai",
            model="dall-e-3",
        )
        agent = Agent(
            name="e2e_image_openai",
            model=model,
            instructions="Generate images when asked. Call the gen_image tool.",
            tools=[img],
        )

        _assert_tool_compiled(runtime, agent, "generate_image", "dall-e-3", "Image/OpenAI")

        result = runtime.run(
            agent,
            'Generate an image of a red circle on a white background. Use size "1024x1024".',
            timeout=TIMEOUT,
        )
        _assert_media_generated(result, "Image/OpenAI", "GENERATE_IMAGE")

    # ── Image: Gemini ─────────────────────────────────────────────────

    def test_image_gemini(self, runtime, model):
        """Generate image via Google Gemini Imagen 3."""
        if not os.environ.get("GOOGLE_AI_API_KEY"):
            pytest.skip("GOOGLE_AI_API_KEY not set")

        img = image_tool(
            name="gen_image_gemini",
            description="Generate an image using Gemini Imagen.",
            llm_provider="google_gemini",
            model="imagen-3.0-generate-002",
        )
        agent = Agent(
            name="e2e_image_gemini",
            model=model,
            instructions="Generate images when asked. Call the gen_image_gemini tool.",
            tools=[img],
        )

        _assert_tool_compiled(runtime, agent, "generate_image", "imagen-3.0-generate-002", "Image/Gemini")

        result = runtime.run(
            agent,
            "Generate an image of a blue square on a white background.",
            timeout=TIMEOUT,
        )
        _assert_media_generated(result, "Image/Gemini", "GENERATE_IMAGE")

    # ── Audio: OpenAI ─────────────────────────────────────────────────

    def test_audio_openai(self, runtime, model):
        """Generate audio via OpenAI TTS-1."""
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        aud = audio_tool(
            name="gen_audio",
            description="Convert text to speech audio.",
            llm_provider="openai",
            model="tts-1",
        )
        agent = Agent(
            name="e2e_audio_openai",
            model=model,
            instructions="Convert text to speech when asked. Call the gen_audio tool.",
            tools=[aud],
        )

        _assert_tool_compiled(runtime, agent, "generate_audio", "tts-1", "Audio/OpenAI")

        result = runtime.run(
            agent,
            'Convert this text to speech: "Hello, this is an end to end test."',
            timeout=TIMEOUT,
        )
        _assert_media_generated(result, "Audio/OpenAI", "GENERATE_AUDIO")

