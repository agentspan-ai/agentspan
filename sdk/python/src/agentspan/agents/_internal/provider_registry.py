# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Provider registry — metadata for auto-registering LLM integrations.

Maps known LLM provider names (as used in ``"provider/model"`` strings) to the
configuration required to create integrations on the Conductor server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ProviderSpec:
    """Metadata for an LLM provider integration.

    Attributes:
        name: SDK provider name (matches :data:`model_parser.KNOWN_PROVIDERS`).
        integration_type: Conductor server ``type`` field for the integration.
        display_name: Human-readable provider name.
        api_key_env: Environment variable that holds the provider's API key.
    """

    name: str
    integration_type: str
    display_name: str
    api_key_env: str


PROVIDER_REGISTRY: Dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        name="openai",
        integration_type="openai",
        display_name="OpenAI",
        api_key_env="OPENAI_API_KEY",
    ),
    "anthropic": ProviderSpec(
        name="anthropic",
        integration_type="anthropic",
        display_name="Anthropic",
        api_key_env="ANTHROPIC_API_KEY",
    ),
    "google_gemini": ProviderSpec(
        name="google_gemini",
        integration_type="google_gemini",
        display_name="Google Gemini",
        api_key_env="GOOGLE_GEMINI_API_KEY",
    ),
}


def get_provider_spec(provider_name: str) -> Optional[ProviderSpec]:
    """Look up a provider spec by name.

    Returns ``None`` if the provider is not in the registry.
    """
    return PROVIDER_REGISTRY.get(provider_name)


# Mirrors server-side CredentialEnvSeeder.KNOWN_ENV_VARS — the full set of
# provider API key env vars the runtime will sync into the local server's
# credential store on boot. Keep in sync with the Java list.
KNOWN_PROVIDER_ENV_VARS: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "XAI_API_KEY",
        "PERPLEXITY_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "HUGGINGFACE_API_KEY",
        "GROQ_API_KEY",
        "DEEPSEEK_API_KEY",
        "TOGETHER_API_KEY",
    }
)
