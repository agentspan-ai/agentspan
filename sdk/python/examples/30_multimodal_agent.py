# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Multimodal Agent — analyze images and video with vision-capable models.

Demonstrates multimodal input via the ``media`` parameter on
``runtime.run()``.  Pass image or video URLs alongside your text prompt —
the Conductor server includes them in the ChatMessage ``media`` field,
enabling vision-capable models (GPT-4o, Gemini, Claude) to see them.

Supported media types:
    - Images: JPEG, PNG, GIF, WebP (URL or data URI)
    - Video: MP4, MOV (provider-dependent, e.g. Gemini)
    - Audio: MP3, WAV (provider-dependent)

Requirements:
    - Conductor server with LLM support (OpenAI key configured)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings

# ── Example 1: Simple image analysis ─────────────────────────────────

vision_agent = Agent(
    name="vision_analyst",
    model=settings.llm_model,
    instructions=(
        "You are a visual analysis expert. Describe images in detail, "
        "noting composition, colors, subjects, and any text visible."
    ),
)

# ── Example 2: Image analysis with tools ─────────────────────────────

@tool
def search_similar(description: str) -> str:
    """Search for similar images based on a description."""
    return f"Found 3 similar images matching: '{description}'"


@tool
def save_analysis(title: str, analysis: str) -> str:
    """Save an image analysis report."""
    return f"Saved analysis '{title}': {analysis[:100]}..."


vision_with_tools = Agent(
    name="vision_researcher",
    model=settings.llm_model,
    instructions=(
        "You are a visual research assistant. Analyze images, search for "
        "similar ones, and save your findings. Always save your analysis."
    ),
    tools=[search_similar, save_analysis],
)

# ── Example 3: Multi-image comparison ────────────────────────────────

comparator = Agent(
    name="image_comparator",
    model=settings.llm_model,
    instructions=(
        "You are an image comparison specialist. When given multiple images, "
        "compare and contrast them in detail: similarities, differences, "
        "style, composition, and subject matter."
    ),
)

# ── Example 4: Multi-agent pipeline with vision ──────────────────────
# First agent describes the image, second generates a creative story

describer = Agent(
    name="describer",
    model=settings.llm_model,
    instructions="Describe the image in 2-3 vivid sentences.",
)

storyteller = Agent(
    name="storyteller",
    model=settings.llm_model,
    instructions=(
        "You receive an image description. Write a short creative "
        "story (3-4 sentences) inspired by it."
    ),
)

creative_pipeline = describer >> storyteller

# ── Run ──────────────────────────────────────────────────────────────

# Sample public-domain images for demonstration
SAMPLE_IMAGE = "https://orkes.io/Home-Page-Prompt-to-Workflow-1.png"
SAMPLE_IMAGE_2 = "https://orkes.io/icons/hero-section-workflow_updated.png"


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.30_multimodal_agent
        runtime.deploy(vision_agent)
        runtime.serve(vision_agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # # --- 1. Single image analysis ---
        # print("=== Single Image Analysis ===")
        # result = runtime.run(
        #     vision_agent,
        #     "What do you see in this image? Describe it in detail.",
        #     media=[SAMPLE_IMAGE],
        # )
        # result.print_result()

        # # --- 2. Image analysis with tools ---
        # print("\n=== Image Analysis with Tools ===")
        # result = runtime.run(
        #     vision_with_tools,
        #     "Analyze this image, search for similar ones, and save your findings.",
        #     media=[SAMPLE_IMAGE],
        # )
        # result.print_result()

        # # --- 3. Compare multiple images ---
        # print("\n=== Multi-Image Comparison ===")
        # result = runtime.run(
        #     comparator,
        #     "Compare these two images. What are the key differences?",
        #     media=[SAMPLE_IMAGE, SAMPLE_IMAGE_2],
        # )
        # result.print_result()

        # # --- 4. Creative pipeline from image ---
        # print("\n=== Creative Pipeline (describe → story) ===")
        # result = runtime.run(
        #     creative_pipeline,
        #     "Create a story inspired by this image.",
        #     media=[SAMPLE_IMAGE_2],
        # )
        # result.print_result()

