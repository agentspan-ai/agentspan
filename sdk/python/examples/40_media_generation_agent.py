# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""
Media Generation Agent — generate images, audio, and video using AI models.

Demonstrates Conductor's built-in media generation system tasks
(``GENERATE_IMAGE``, ``GENERATE_AUDIO``, ``GENERATE_VIDEO``) exposed as
native agent tools via ``image_tool()``, ``audio_tool()``, and
``video_tool()``.  These are **server-side** tools — no worker process
is needed.

Architecture:
    orchestrator agent
        tools: generate_image  (DALL-E 3)
               text_to_speech  (OpenAI TTS)
               generate_video  (OpenAI Sora)

Requirements:
    - Conductor server with OpenAI integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, audio_tool, image_tool, video_tool
from settings import settings

# ── Media generation tools (server-side, no worker needed) ────────────

gen_image = image_tool(
    name="generate_image",
    description="Generate an image from a text description using DALL-E 3.",
    llm_provider="openai",
    model="dall-e-3",
)

gen_audio = audio_tool(
    name="text_to_speech",
    description="Convert text to natural-sounding speech audio using OpenAI TTS.",
    llm_provider="openai",
    model="tts-1",
)

gen_video = video_tool(
    name="generate_video",
    description="Generate a short video clip from a text description using OpenAI Sora.",
    llm_provider="openai",
    model="sora-2",
    size="1280x720",
    n=1,
)

# ── Orchestrator Agent ────────────────────────────────────────────────

media_agent = Agent(
    name="media_generator",
    model=settings.llm_model,
    tools=[gen_image, gen_audio, gen_video],
    instructions=(
        "You are a creative media generation assistant. You can generate:\n\n"
        "1. **Images** — from text descriptions using DALL-E 3.\n"
        "2. **Audio** — text-to-speech using OpenAI TTS "
        "(voices: alloy, echo, fable, onyx, nova, shimmer).\n"
        "3. **Video** — short video clips from text using OpenAI Sora.\n\n"
        "IMPORTANT: Image prompts MUST be under 950 characters.\n"
        "Call the appropriate tool once and present the result."
    ),
)

# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Media Generation Agent")
    print("=" * 60)

    with AgentRuntime() as runtime:
        result = runtime.run(
            media_agent,
            (
                "Create an image of a serene Japanese garden with a koi pond "
                "at sunset, cherry blossoms falling gently. Use vivid style."
                "use that image to generate a video with audio narration describing the image"
            ),
        )
        result.print_result()
