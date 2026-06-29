# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Parse ``"provider/model"`` strings into (provider, model) tuples.

Conductor's :class:`LlmChatComplete` requires separate ``llm_provider`` and
``model`` arguments.  This module handles the unified format used by the
agents SDK.
"""

from __future__ import annotations

from dataclasses import dataclass

# Known Conductor LLM provider names.
KNOWN_PROVIDERS = frozenset(
    {
        "openai",
        "azure_openai",
        "anthropic",
        "google_gemini",
        "google_vertex_ai",
        "aws_bedrock",
        "cohere",
        "mistral",
        "groq",
        "perplexity",
        "hugging_face",
        "deepseek",
    }
)


@dataclass(frozen=True)
class ParsedModel:
    """Result of parsing a ``"provider/model"`` string.

    Attributes:
        provider: The Conductor integration name (e.g. ``"openai"``).
        model: The model identifier (e.g. ``"gpt-4o"``).
    """

    provider: str
    model: str


def parse_model(model_string: str) -> ParsedModel:
    """Parse a ``"provider/model"`` string.

    Args:
        model_string: A string in ``"provider/model"`` format, e.g.
            ``"openai/gpt-4o"`` or ``"anthropic/claude-sonnet-4-20250514"``.

    Returns:
        A :class:`ParsedModel` with separate ``provider`` and ``model`` fields.

    Raises:
        ValueError: If the string is not in the expected format.

    Examples::

        >>> parse_model("openai/gpt-4o")
        ParsedModel(provider='openai', model='gpt-4o')

        >>> parse_model("anthropic/claude-sonnet-4-20250514")
        ParsedModel(provider='anthropic', model='claude-sonnet-4-20250514')

        >>> parse_model("azure_openai/gpt-4o")
        ParsedModel(provider='azure_openai', model='gpt-4o')
    """
    if "/" not in model_string:
        raise ValueError(
            f"Invalid model format {model_string!r}. "
            "Expected 'provider/model' (e.g. 'openai/gpt-4o')"
        )

    parts = model_string.split("/", 1)
    provider = parts[0].strip()
    model = parts[1].strip()

    if not provider:
        raise ValueError(f"Empty provider in model string {model_string!r}")
    if not model:
        raise ValueError(f"Empty model name in model string {model_string!r}")

    return ParsedModel(provider=provider, model=model)
