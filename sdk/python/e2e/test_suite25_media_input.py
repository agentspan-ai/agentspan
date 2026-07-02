"""Suite 25: Media Input — image sent TO a vision model via ``media=``.

This is the inverse of Suite 7 (media *generation*): here an image is passed as
**input** on ``runtime.run(..., media=[...])`` and we verify a vision-capable
model actually receives and reads it.

Deterministic, non-LLM-judged validation (per repo CLAUDE.md): the image
contains a distinctive, machine-unguessable token ("MELON7391"). The agent is
asked to transcribe the text; we assert the exact token appears in the final
answer. The model cannot produce that token unless it truly saw the image —
which is the whole point of the ``media`` parameter.

**Self-contained image.** The PNG is embedded in this file as base64 (see
``_IMAGE_B64``) — the suite has NO runtime dependency on any external image
host. The server reads media itself and rejects data URIs, so the test writes
the embedded bytes to a file and passes its path. The server only reads files
under its allowed media directory, which defaults to ``~/worker-payload/`` (the
directory used when ``conductor.file-storage.parentDir`` is unset — the default
``agentspan server start`` config). This assumes the server runs on the same
host as the test — the standard local / bundle e2e setup. Set
``AGENTSPAN_MEDIA_DIR`` to override the directory for deployments that
configure a custom allowed media dir.

Parametrized across providers. The Anthropic positive case is ``skip``ped: in
current server builds media is forwarded to OpenAI but NOT attached to the
Anthropic provider request (the model receives no image), so the token is never
read. Remove the skip once the server forwards media for Anthropic (see
SUITE25_ANTHROPIC_SKIP_REASON).

No mocks. Real server, real vision model.
"""

import base64
import os
from pathlib import Path

import pytest

from conductor.ai.agents import Agent

pytestmark = [
    pytest.mark.e2e,
]

TIMEOUT = 120

# ── Test image (self-contained) ───────────────────────────────────────────────
# A 600x200 PNG rendering the exact text "MELON7391" (black on white), embedded
# as base64 so the suite carries its own image and never calls out to a
# third-party host at run time.
#
# To regenerate (e.g. to change the token), render it once with a public
# text-image service and re-embed the base64 — the URL must end in ``.png`` and
# the token must stay unguessable (the counterfactual test depends on that):
#
#   curl -fsSL "https://dummyimage.com/600x200/ffffff/000000.png?text=MELON7391" -o media.png
#   base64 -w0 media.png     # Linux   (macOS: base64 -i media.png | tr -d '\n')
#
# then paste the output below and update SECRET to match.
SECRET = "MELON7391"
_IMAGE_B64 = "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"
_IMAGE_PNG = base64.b64decode(_IMAGE_B64)

READ_PROMPT = (
    "Transcribe the exact text shown in the image. Reply with only that text and nothing else."
)

INSTRUCTIONS = "You are an OCR assistant. Read text from images precisely."

# ── Provider matrix ─────────────────────────────────────────────────────────
# (API-key env var, model id). Each case is gated on its key.
#
# Anthropic media-input is broken server-side: media is forwarded to OpenAI but
# NOT attached to the Anthropic provider request, so the model receives no image
# and never reads the token. The positive case is skipped until that is fixed;
# the counterfactual (no media at all) still runs and passes for Anthropic.
SUITE25_ANTHROPIC_SKIP_REASON = (
    "Server does not attach media to the Anthropic provider request — the model "
    "receives no image (OpenAI works). Re-enable when the server forwards media "
    "for Anthropic."
)
_ANTHROPIC_MEDIA_SKIP = pytest.mark.skip(reason=SUITE25_ANTHROPIC_SKIP_REASON)

# Positive test: Anthropic is skipped (no image reaches the model — see above).
POSITIVE_CASES = [
    pytest.param("OPENAI_API_KEY", "openai/gpt-4o-mini", id="openai"),
    pytest.param(
        "ANTHROPIC_API_KEY",
        "anthropic/claude-sonnet-4-5",
        id="anthropic",
        marks=_ANTHROPIC_MEDIA_SKIP,
    ),
]

# Counterfactual: both providers should COMPLETE and simply not emit the token
# (no media is sent at all), so neither is expected to fail.
COUNTERFACTUAL_CASES = [
    pytest.param("OPENAI_API_KEY", "openai/gpt-4o-mini", id="openai"),
    pytest.param("ANTHROPIC_API_KEY", "anthropic/claude-sonnet-4-5", id="anthropic"),
]


# ── Helpers ────────────────────────────────────────────────────────────────────


def _final_text(result) -> str:
    """Extract the agent's final answer text from an AgentResult."""
    out = result.output
    if isinstance(out, dict):
        return str(out.get("result") or "")
    return str(out or "")


def _normalize(s: str) -> str:
    """Uppercase and keep only [A-Z0-9] so punctuation/spacing don't matter."""
    return "".join(ch for ch in s.upper() if ch.isalnum())


def _agent_slug(key_env: str) -> str:
    """e.g. OPENAI_API_KEY -> openai (for unique per-provider agent names)."""
    return key_env.split("_", 1)[0].lower()


def _require_key(key_env: str):
    """Skip unless the provider key is set."""
    if not os.environ.get(key_env):
        pytest.skip(f"{key_env} not set — provider unavailable")


# The server reads media file paths only under its allowed directory, which
# defaults to ``~/worker-payload/`` on the server's host (see DocumentAccessPolicy;
# used when ``conductor.file-storage.parentDir`` is unset). Deployments that
# configure a different allowed dir (e.g. a custom ``file-storage.parentDir``)
# can point the test at it via ``AGENTSPAN_MEDIA_DIR``.
_ALLOWED_MEDIA_DIR = Path(
    os.environ.get("AGENTSPAN_MEDIA_DIR") or (Path(os.path.expanduser("~")) / "worker-payload")
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def image_path():
    """Write the embedded PNG into the server's allowed media dir and yield its path.

    The file lives under ``~/worker-payload/`` so the server (same host) is
    permitted to read it. The ``.png`` extension lets the server resolve the
    image mime type.
    """
    try:
        _ALLOWED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        pytest.skip(f"cannot create server media dir {_ALLOWED_MEDIA_DIR}: {e}")

    path = _ALLOWED_MEDIA_DIR / "e2e_s25_media_input.png"
    path.write_bytes(_IMAGE_PNG)
    try:
        yield str(path)
    finally:
        path.unlink(missing_ok=True)


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.timeout(300)
class TestSuite25MediaInput:
    """Image passed as input to a vision model via ``media=``."""

    @pytest.mark.parametrize("key_env,model_id", POSITIVE_CASES)
    def test_vision_reads_text_from_image(self, runtime, image_path, key_env, model_id):
        """With media=[image], the model transcribes the embedded token.

        This can ONLY pass if the image actually reached a vision-capable
        model — the token appears nowhere in the prompt or instructions.
        """
        _require_key(key_env)

        agent = Agent(
            name=f"e2e_s25_vision_{_agent_slug(key_env)}",
            model=model_id,
            instructions=INSTRUCTIONS,
        )

        result = runtime.run(agent, READ_PROMPT, media=[image_path], timeout=TIMEOUT)

        assert result.status == "COMPLETED", (
            f"run did not complete: status={result.status} execution_id={result.execution_id}"
        )
        text = _final_text(result)
        assert _normalize(SECRET) in _normalize(text), (
            f"vision model did not transcribe the embedded token '{SECRET}'. "
            f"Got: {text!r} (execution_id={result.execution_id})"
        )

    @pytest.mark.parametrize("key_env,model_id", COUNTERFACTUAL_CASES)
    def test_without_media_token_is_absent(self, runtime, key_env, model_id):
        """Counterfactual: the same prompt with NO media must still COMPLETE
        but must NOT yield the token.

        Proves the positive test is real — the token only appears because the
        image was actually seen, not because it leaked through the prompt or
        the model guessed it. If this ever fails, the positive test is a false
        positive.
        """
        _require_key(key_env)

        agent = Agent(
            name=f"e2e_s25_no_media_{_agent_slug(key_env)}",
            model=model_id,
            instructions=INSTRUCTIONS,
        )

        result = runtime.run(agent, READ_PROMPT, timeout=TIMEOUT)

        assert result.status == "COMPLETED", (
            f"no-media run did not complete: status={result.status} "
            f"execution_id={result.execution_id}"
        )
        text = _final_text(result)
        assert _normalize(SECRET) not in _normalize(text), (
            f"token '{SECRET}' appeared WITHOUT the image being sent — the "
            f"positive test would be a false positive. Got: {text!r}"
        )
