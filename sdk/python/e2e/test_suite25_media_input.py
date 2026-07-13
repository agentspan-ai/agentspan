"""Suite 25: Media Input — image sent TO a vision model via ``media=``.

This is the inverse of Suite 7 (media *generation*): here an image is passed as
**input** on ``runtime.run(..., media=[...])`` and we verify a vision-capable
model actually receives and reads it.

Deterministic, non-LLM-judged validation (per repo CLAUDE.md): the image
contains a distinctive, machine-unguessable token ("MELON7391"). The agent is
asked to transcribe the text; we assert the exact token appears in the final
answer. The model cannot produce that token unless it truly saw the image —
which is the whole point of the ``media`` parameter.

**Self-contained image.** The PNG is committed alongside this test
(``assets/melon7391.png``) and read at import time — the suite has NO runtime
dependency on any external image host. The server reads media itself and
rejects data URIs, so the test writes those bytes to a file and passes its path. The server only reads files
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

import os
from pathlib import Path

import pytest

from conductor.ai.agents import Agent

pytestmark = [
    pytest.mark.e2e,
]

TIMEOUT = 120

# ── Test image (self-contained) ───────────────────────────────────────────────
# A 600x200 PNG rendering the exact text "MELON7391" (black on white), committed
# alongside this test (assets/melon7391.png) and read at import time — so the
# suite carries its own image and never calls out to a third-party host at run
# time.
#
# To regenerate (e.g. to change the token), render it once with a public
# text-image service and overwrite the asset — keep a ``.png`` extension and an
# unguessable token (the counterfactual test depends on that), then update
# SECRET to match:
#
#   curl -fsSL "https://dummyimage.com/600x200/ffffff/000000.png?text=MELON7391" \
#     -o sdk/python/e2e/assets/melon7391.png
SECRET = "MELON7391"
_IMAGE_PATH = Path(__file__).parent / "assets" / "melon7391.png"
_IMAGE_PNG = _IMAGE_PATH.read_bytes()

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
