# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Short Movie Pipeline — sequential content generation stages.

Demonstrates:
    - SequentialAgent with 5 specialized stages
    - Each stage builds on previous output (concept → script → visuals → audio → assembly)
    - Tools at each stage for structured output

Inspired by the Google ADK short-movie-agents sample which uses
a multi-stage pipeline for creative content production.

Requirements:
    - pip install google-adk
    - Conductor server
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent, SequentialAgent

from agentspan.agents import AgentRuntime

from settings import settings


# ── Stage tools ──────────────────────────────────────────────────

def create_concept(title: str, genre: str, logline: str) -> dict:
    """Create a movie concept document.

    Args:
        title: Working title for the short film.
        genre: Genre (e.g., sci-fi, drama, comedy).
        logline: One-sentence summary of the story.

    Returns:
        Dictionary with the structured concept.
    """
    return {
        "concept": {
            "title": title,
            "genre": genre,
            "logline": logline,
            "status": "approved",
        }
    }


def write_scene(scene_number: int, location: str, action: str,
                dialogue: str = "") -> dict:
    """Write a single scene for the script.

    Args:
        scene_number: Scene number in sequence.
        location: Scene location description.
        action: Action/direction description.
        dialogue: Optional dialogue for the scene.

    Returns:
        Dictionary with the formatted scene.
    """
    scene = {
        "scene": scene_number,
        "location": location,
        "action": action,
    }
    if dialogue:
        scene["dialogue"] = dialogue
    return {"scene": scene}


def describe_visual(scene_number: int, shot_type: str,
                    description: str) -> dict:
    """Describe visual direction for a scene.

    Args:
        scene_number: Which scene this visual is for.
        shot_type: Camera shot type (wide, close-up, tracking, etc.).
        description: Visual description including lighting, color, mood.

    Returns:
        Dictionary with the visual direction.
    """
    return {
        "visual": {
            "scene": scene_number,
            "shot_type": shot_type,
            "description": description,
        }
    }


def specify_audio(scene_number: int, music_mood: str,
                  sound_effects: str) -> dict:
    """Specify audio direction for a scene.

    Args:
        scene_number: Which scene this audio is for.
        music_mood: Music mood/style description.
        sound_effects: Key sound effects needed.

    Returns:
        Dictionary with the audio specification.
    """
    return {
        "audio": {
            "scene": scene_number,
            "music_mood": music_mood,
            "sound_effects": sound_effects,
        }
    }


def assemble_production(title: str, total_scenes: int,
                        estimated_runtime: str) -> dict:
    """Assemble final production notes.

    Args:
        title: Final title of the short film.
        total_scenes: Number of scenes in the final cut.
        estimated_runtime: Estimated runtime (e.g., "3 minutes").

    Returns:
        Dictionary with production assembly notes.
    """
    return {
        "production": {
            "title": title,
            "total_scenes": total_scenes,
            "estimated_runtime": estimated_runtime,
            "status": "ready_for_production",
        }
    }


# ── Pipeline stages ──────────────────────────────────────────────

concept_developer = Agent(
    name="concept_developer",
    model=settings.llm_model,
    instruction=(
        "You are a creative director. Develop a concept for a short film "
        "based on the given theme. Use create_concept to document the "
        "title, genre, and logline. Keep it concise and compelling."
    ),
    tools=[create_concept],
)

scriptwriter = Agent(
    name="scriptwriter",
    model=settings.llm_model,
    instruction=(
        "You are a scriptwriter. Based on the concept from the previous "
        "stage, write 3 short scenes using write_scene for each. "
        "Include location, action, and brief dialogue."
    ),
    tools=[write_scene],
)

visual_director = Agent(
    name="visual_director",
    model=settings.llm_model,
    instruction=(
        "You are a visual director. For each scene written by the "
        "scriptwriter, use describe_visual to specify camera shots, "
        "lighting, and visual mood. Create one visual spec per scene."
    ),
    tools=[describe_visual],
)

audio_designer = Agent(
    name="audio_designer",
    model=settings.llm_model,
    instruction=(
        "You are an audio designer. For each scene, use specify_audio "
        "to define the music mood and key sound effects. Match the "
        "audio to the visual mood described by the visual director."
    ),
    tools=[specify_audio],
)

producer = Agent(
    name="producer",
    model=settings.llm_model,
    instruction=(
        "You are the producer. Review all previous stages and use "
        "assemble_production to create final production notes. "
        "Summarize the complete short film with all creative elements."
    ),
    tools=[assemble_production],
)

# Full pipeline: concept → script → visuals → audio → assembly
movie_pipeline = SequentialAgent(
    name="short_movie_pipeline",
    sub_agents=[concept_developer, scriptwriter, visual_director,
                audio_designer, producer],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        movie_pipeline,
        "Create a 3-scene short film about a robot discovering music "
        "for the first time in a post-apocalyptic world.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(movie_pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.adk.28_movie_pipeline
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(movie_pipeline)
