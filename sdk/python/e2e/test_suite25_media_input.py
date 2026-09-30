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

Parametrized across providers, each gated on its API key. Which providers
actually forward image input server-side is documented in the provider matrix
below (determined by reading each provider's conductor-ai ChatModel). OpenAI
forwards media and runs; Anthropic's converter currently drops it, so its
positive case is ``skip``ped with a documented reason. The counterfactual (no
media) runs for all parametrized providers.

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
# Whether a provider supports image *input* is decided by its conductor-ai
# ChatModel: does the message converter forward ``UserMessage.getMedia()``, or
# only ``getText()``? Determined by reading each provider's chat model in
# conductor-ai (org.conductoross.conductor.ai.providers.*):
#
#   FORWARDS media (image reaches the model) — mapped by the provider ChatModel:
#     openai       OpenAIResponsesChatModel        -> input_image content parts
#     azureopenai  reuses OpenAIResponsesChatModel  -> input_image content parts
#     mistral      Spring AI MistralAiChatModel     -> image_url MediaContent
#     ollama       Spring AI OllamaChatModel        -> images (base64)
#     bedrock      Spring AI BedrockProxyChatModel  -> mapMediaToContentBlock/ImageBlock
#
#   (mistral/ollama/bedrock media handling lives in the Spring AI framework, not
#   a conductor-ai converter — see Spring AI multimodality:
#   https://docs.spring.io/spring-ai/reference/api/multimodality.html
#   For bedrock a URL is fetched by spring-ai's MediaFetcher — SSRF-guarded:
#   blocks loopback/link-local, 40 MB cap — though conductor-ai usually
#   pre-downloads media to bytes first. MediaFetcher exists only in newer
#   spring-ai; the versions resolved here (1.0.2/1.1.2) map bytes/URL without it.)
#
#   DROPS media (custom converter emits text only — image never sent):
#     anthropic    AnthropicChatModel.convertMessage  -> Message.user(getText())
#                  [fixed in conductor-oss#1238, pending release]
#     gemini       GeminiChatModel.convertMessage     -> Part.text(getText())
#                  [same bug; fixed in conductor-oss#1241, pending release]
#     cohere       CohereChatModel        -> new ChatMessage(role, getText())
#                  [vision-capable (e.g. command-a-vision); the request DTO's
#                  content was a bare String. Fixed in conductor-oss#1246,
#                  pending release]
#     huggingface  HuggingFaceChatModel   -> api.generate({inputs}); legacy
#                  text-generation, no messages/roles/media (see note)
#     grok         OpenAICompatChatModel  -> MessageItem.user(getText())
#                  [fixed in conductor-oss#1243, pending release]
#     perplexity   reuses OpenAICompatChatModel
#                  [same fix; conductor-oss#1243]
#
#   (huggingface DOES support multimodal, but only via its OpenAI-compatible
#   router endpoint https://router.huggingface.co/v1/responses (input_text/
#   input_image). The legacy provider used the text-generation API
#   ({inputs} -> generated_text) and carried neither messages nor media;
#   conductor-oss#1245 migrates it to the router (reusing OpenAIResponsesChatModel),
#   which is a provider migration, not a converter tweak. Image support is
#   model-dependent.)
#
#   Out of scope — image-GENERATION-only providers (e.g. stabilityai): no chat
#   model at all (getChatModel throws UnsupportedOperationException), so there is
#   no media-input path. They produce images (cf. Suite 7), they don't receive
#   them.
#
# Cases below exercise OpenAI (runnable with a single API key here) plus
# Anthropic, tracked as a skip until conductor-oss#1238 ships. Every other
# provider is documented above but not parametrized — none can be exercised
# here: azure/mistral/ollama/bedrock need provider-specific credentials or a
# running server, and gemini (fix: conductor-oss#1241) has no API key available.
_ANTHROPIC_SKIP_REASON = (
    "Server does not attach media to the Anthropic provider request — the model "
    "receives no image (OpenAI works). Fixed in conductor-oss#1238; re-enable "
    "once the server ships it."
)
# Kept for back-compat with anything referencing the original name.
SUITE25_ANTHROPIC_SKIP_REASON = _ANTHROPIC_SKIP_REASON
_ANTHROPIC_MEDIA_SKIP = pytest.mark.skip(reason=_ANTHROPIC_SKIP_REASON)

# Positive test: only OpenAI reaches the model with the image today; Anthropic
# is skipped (see reason above). Gemini is out — same server bug (fix:
# conductor-oss#1241) but no GOOGLE_AI_API_KEY available to exercise it.
POSITIVE_CASES = [
    pytest.param("OPENAI_API_KEY", "openai/gpt-4o-mini", id="openai"),
    pytest.param(
        "ANTHROPIC_API_KEY",
        "anthropic/claude-sonnet-4-5",
        id="anthropic",
        marks=_ANTHROPIC_MEDIA_SKIP,
    ),
]

# Counterfactual: with NO media every provider should COMPLETE and simply not
# emit the token, so none are skipped here (each still gates on its key).
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
