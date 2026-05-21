// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example Adk 28 — Short Movie Pipeline
 *
 * <p>Java port of <code>sdk/python/examples/adk/28_movie_pipeline.py</code>.
 *
 * <p>Demonstrates: a SequentialAgent-style pipeline with 5 stages
 * (concept → script → visuals → audio → assembly).
 */
public class Example28MoviePipeline {

    @Schema(description = "Create a movie concept document.")
    public static Map<String, Object> createConcept(
            @Schema(name = "title", description = "Title of the film") String title,
            @Schema(name = "genre", description = "Film genre") String genre,
            @Schema(name = "logline", description = "One-sentence summary") String logline) {
        return Map.of("concept", Map.of(
            "title", title,
            "genre", genre,
            "logline", logline,
            "status", "approved"
        ));
    }

    @Schema(description = "Write a single scene for the script.")
    public static Map<String, Object> writeScene(
            @Schema(name = "scene_number", description = "Scene number") int sceneNumber,
            @Schema(name = "location", description = "Scene location") String location,
            @Schema(name = "action", description = "Action description") String action,
            @Schema(name = "dialogue", description = "Dialogue text (optional)") String dialogue) {
        Map<String, Object> scene = new LinkedHashMap<>();
        scene.put("scene", sceneNumber);
        scene.put("location", location);
        scene.put("action", action);
        if (dialogue != null && !dialogue.isEmpty()) {
            scene.put("dialogue", dialogue);
        }
        return Map.of("scene", scene);
    }

    @Schema(description = "Describe visual direction for a scene.")
    public static Map<String, Object> describeVisual(
            @Schema(name = "scene_number", description = "Scene number") int sceneNumber,
            @Schema(name = "shot_type", description = "Camera shot type") String shotType,
            @Schema(name = "description", description = "Visual description") String description) {
        return Map.of("visual", Map.of(
            "scene", sceneNumber,
            "shot_type", shotType,
            "description", description
        ));
    }

    @Schema(description = "Specify audio direction for a scene.")
    public static Map<String, Object> specifyAudio(
            @Schema(name = "scene_number", description = "Scene number") int sceneNumber,
            @Schema(name = "music_mood", description = "Music mood") String musicMood,
            @Schema(name = "sound_effects", description = "Sound effects") String soundEffects) {
        return Map.of("audio", Map.of(
            "scene", sceneNumber,
            "music_mood", musicMood,
            "sound_effects", soundEffects
        ));
    }

    @Schema(description = "Assemble final production notes.")
    public static Map<String, Object> assembleProduction(
            @Schema(name = "title", description = "Film title") String title,
            @Schema(name = "total_scenes", description = "Number of scenes") int totalScenes,
            @Schema(name = "estimated_runtime", description = "Estimated runtime") String estimatedRuntime) {
        return Map.of("production", Map.of(
            "title", title,
            "total_scenes", totalScenes,
            "estimated_runtime", estimatedRuntime,
            "status", "ready_for_production"
        ));
    }

    public static void main(String[] args) {
        LlmAgent conceptDeveloper = LlmAgent.builder()
            .name("concept_developer")
            .description("Develops a film concept with title, genre, and logline.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a creative director. Develop a concept for a short film
                based on the given theme. Use create_concept to document the
                title, genre, and logline. Keep it concise and compelling.
                """)
            .tools(FunctionTool.create(Example28MoviePipeline.class, "createConcept"))
            .outputKey("film_concept")
            .build();

        LlmAgent scriptwriter = LlmAgent.builder()
            .name("scriptwriter")
            .description("Writes 3 short scenes from the approved film concept.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a scriptwriter. Based on the concept from the previous
                stage, write 3 short scenes using write_scene for each.
                Include location, action, and brief dialogue.
                """)
            .tools(FunctionTool.create(Example28MoviePipeline.class, "writeScene"))
            .outputKey("script_scenes")
            .build();

        LlmAgent visualDirector = LlmAgent.builder()
            .name("visual_director")
            .description("Specifies camera shots, lighting, and visual mood for each scene.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a visual director. For each scene written by the
                scriptwriter, use describe_visual to specify camera shots,
                lighting, and visual mood. Create one visual spec per scene.
                """)
            .tools(FunctionTool.create(Example28MoviePipeline.class, "describeVisual"))
            .outputKey("visual_direction")
            .build();

        LlmAgent audioDesigner = LlmAgent.builder()
            .name("audio_designer")
            .description("Designs music mood and sound effects to match the visual direction.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are an audio designer. For each scene, use specify_audio
                to define the music mood and key sound effects. Match the
                audio to the visual mood described by the visual director.
                """)
            .tools(FunctionTool.create(Example28MoviePipeline.class, "specifyAudio"))
            .outputKey("audio_direction")
            .build();

        LlmAgent producer = LlmAgent.builder()
            .name("producer")
            .description("Assembles final production notes summarizing all creative elements.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are the producer. Review all previous stages and use
                assemble_production to create final production notes.
                Summarize the complete short film with all creative elements.
                """)
            .tools(FunctionTool.create(Example28MoviePipeline.class, "assembleProduction"))
            .outputKey("production_notes")
            .build();

        LlmAgent moviePipeline = LlmAgent.builder()
            .name("short_movie_pipeline")
            .description("Five-stage short-film pipeline: concept → script → visuals → audio → producer.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate a short-movie production pipeline. Run the stages in order: "
                + "concept_developer → scriptwriter → visual_director → audio_designer → producer.")
            .subAgents(conceptDeveloper, scriptwriter, visualDirector, audioDesigner, producer)
            .build();

        AgentResult result = Agentspan.run(moviePipeline,
            "Create a 3-scene short film about a robot discovering music "
            + "for the first time in a post-apocalyptic world.");
        result.printResult();

        Agentspan.shutdown();
    }
}
