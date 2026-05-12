// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

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
public class ExampleAdk28MoviePipeline {

    static class ConceptTools {
        @Tool(name = "create_concept", value = "Create a movie concept document.")
        public Map<String, Object> createConcept(
                @P("title") String title,
                @P("genre") String genre,
                @P("logline") String logline) {
            return Map.of("concept", Map.of(
                "title", title,
                "genre", genre,
                "logline", logline,
                "status", "approved"
            ));
        }
    }

    static class ScriptTools {
        @Tool(name = "write_scene", value = "Write a single scene for the script.")
        public Map<String, Object> writeScene(
                @P("scene_number") int sceneNumber,
                @P("location") String location,
                @P("action") String action,
                @P("dialogue") String dialogue) {
            Map<String, Object> scene = new LinkedHashMap<>();
            scene.put("scene", sceneNumber);
            scene.put("location", location);
            scene.put("action", action);
            if (dialogue != null && !dialogue.isEmpty()) {
                scene.put("dialogue", dialogue);
            }
            return Map.of("scene", scene);
        }
    }

    static class VisualTools {
        @Tool(name = "describe_visual", value = "Describe visual direction for a scene.")
        public Map<String, Object> describeVisual(
                @P("scene_number") int sceneNumber,
                @P("shot_type") String shotType,
                @P("description") String description) {
            return Map.of("visual", Map.of(
                "scene", sceneNumber,
                "shot_type", shotType,
                "description", description
            ));
        }
    }

    static class AudioTools {
        @Tool(name = "specify_audio", value = "Specify audio direction for a scene.")
        public Map<String, Object> specifyAudio(
                @P("scene_number") int sceneNumber,
                @P("music_mood") String musicMood,
                @P("sound_effects") String soundEffects) {
            return Map.of("audio", Map.of(
                "scene", sceneNumber,
                "music_mood", musicMood,
                "sound_effects", soundEffects
            ));
        }
    }

    static class ProducerTools {
        @Tool(name = "assemble_production", value = "Assemble final production notes.")
        public Map<String, Object> assembleProduction(
                @P("title") String title,
                @P("total_scenes") int totalScenes,
                @P("estimated_runtime") String estimatedRuntime) {
            return Map.of("production", Map.of(
                "title", title,
                "total_scenes", totalScenes,
                "estimated_runtime", estimatedRuntime,
                "status", "ready_for_production"
            ));
        }
    }

    public static void main(String[] args) {
        Agent conceptDeveloper = GoogleADKAgent.builder()
            .name("concept_developer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a creative director. Develop a concept for a short film "
                + "based on the given theme. Use create_concept to document the "
                + "title, genre, and logline. Keep it concise and compelling.")
            .tools(new ConceptTools())
            .build();

        Agent scriptwriter = GoogleADKAgent.builder()
            .name("scriptwriter")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a scriptwriter. Based on the concept from the previous "
                + "stage, write 3 short scenes using write_scene for each. "
                + "Include location, action, and brief dialogue.")
            .tools(new ScriptTools())
            .build();

        Agent visualDirector = GoogleADKAgent.builder()
            .name("visual_director")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a visual director. For each scene written by the "
                + "scriptwriter, use describe_visual to specify camera shots, "
                + "lighting, and visual mood. Create one visual spec per scene.")
            .tools(new VisualTools())
            .build();

        Agent audioDesigner = GoogleADKAgent.builder()
            .name("audio_designer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are an audio designer. For each scene, use specify_audio "
                + "to define the music mood and key sound effects. Match the "
                + "audio to the visual mood described by the visual director.")
            .tools(new AudioTools())
            .build();

        Agent producer = GoogleADKAgent.builder()
            .name("producer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are the producer. Review all previous stages and use "
                + "assemble_production to create final production notes. "
                + "Summarize the complete short film with all creative elements.")
            .tools(new ProducerTools())
            .build();

        Agent moviePipeline = GoogleADKAgent.builder()
            .name("short_movie_pipeline")
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
