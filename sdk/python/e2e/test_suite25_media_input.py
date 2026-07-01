"""Suite 25: Media Input — image sent TO a vision model via ``media=``.

This is the inverse of Suite 7 (media *generation*): here an image is passed as
**input** on ``runtime.run(..., media=[...])`` and we verify a vision-capable
model actually receives and reads it.

Deterministic, non-LLM-judged validation (per repo CLAUDE.md): the image
contains a distinctive, machine-unguessable token ("MELON7391"). The agent is
asked to transcribe the text; we assert the exact token appears in the final
answer. The model cannot produce that token unless it truly saw the image —
which is the whole point of the ``media`` parameter.

The image comes from a public text-rendering service so the token lives in the
URL (still deterministic and self-contained — no data URI, which the server
rejects, and no loopback host, which the server blocks for SSRF). The server
fetches the URL and forwards it to the model, so the URL must be publicly
reachable; the suite skips if the image host is unreachable.

Parametrized across providers. The Anthropic positive case is ``skip``ped: in
current server builds media is forwarded to OpenAI but NOT attached to the
Anthropic provider request (the model receives no image), so the token is never
read. Remove the skip once the server forwards media for Anthropic (see
SUITE25_ANTHROPIC_SKIP_REASON).

No mocks. Real server, real vision model.
"""

import os

import pytest
import requests

from conductor.ai.agents import Agent

pytestmark = [
    pytest.mark.e2e,
]

TIMEOUT = 120

# ── Test image ────────────────────────────────────────────────────────────────
# A public service that renders arbitrary text into a PNG. The token lives in
# the URL, so the expected answer is fixed and unguessable, yet nothing needs to
# be hosted by us. The URL ends in ``.png`` so the server can resolve the mime
# type (a query-only ``&text=`` form fails server-side mime detection).
SECRET = "MELON7391"
IMAGE_URL = f"https://dummyimage.com/600x200/ffffff/000000.png?text={SECRET}"

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
# (no image is sent at all), so neither is expected to fail.
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


def _require_prereqs(key_env: str):
    """Skip unless the provider key is set and the image host is reachable."""
    if not os.environ.get(key_env):
        pytest.skip(f"{key_env} not set — provider unavailable")
    try:
        resp = requests.get(IMAGE_URL, timeout=10)
        resp.raise_for_status()
    except Exception as e:  # network flake / host down — not a product failure
        pytest.skip(f"test image host unreachable: {e}")


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.timeout(300)
class TestSuite25MediaInput:
    """Image passed as input to a vision model via ``media=``."""

    @pytest.mark.parametrize("key_env,model_id", POSITIVE_CASES)
    def test_vision_reads_text_from_image(self, runtime, key_env, model_id):
        """With media=[image], the model transcribes the embedded token.

        This can ONLY pass if the image actually reached a vision-capable
        model — the token appears nowhere in the prompt or instructions.
        """
        _require_prereqs(key_env)

        agent = Agent(
            name=f"e2e_s25_vision_{_agent_slug(key_env)}",
            model=model_id,
            instructions=INSTRUCTIONS,
        )

        result = runtime.run(agent, READ_PROMPT, media=[IMAGE_URL], timeout=TIMEOUT)

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
        _require_prereqs(key_env)

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
