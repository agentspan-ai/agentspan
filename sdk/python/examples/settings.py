# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Shared settings for all examples.

Set ``AGENT_LLM_MODEL`` in a ``.env`` file (recommended) or as an environment
variable to override the default model used by all examples::

    # .env
    AGENT_LLM_MODEL=anthropic/claude-sonnet-4-20250514

    # or set in environment
    AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash

If unset, defaults to ``openai/gpt-4o-mini``.

``AGENT_SECONDARY_LLM_MODEL`` provides a second model for multi-model examples
(e.g., cheap triage vs capable specialist). Defaults to ``openai/gpt-4o``.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_model: str = Field(default="openai/gpt-4o-mini", validation_alias="AGENT_LLM_MODEL")
    secondary_llm_model: str = Field(default="openai/gpt-4o", validation_alias="AGENT_SECONDARY_LLM_MODEL")


settings = Settings()
