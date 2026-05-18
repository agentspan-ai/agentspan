// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.Strategy;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 41 — Sequential Pipeline with Stage-Level Tools
 *
 * <p>Demonstrates the sequential strategy where each sub-agent in the pipeline
 * has its own tools for producing structured output. A movie production pipeline:
 *
 * <pre>
 * concept_developer → scriptwriter → visual_director → audio_designer → producer
 * </pre>
 *
 * Each stage builds on the previous one's output and calls its own tools.
 */
public class Example41SequentialPipelineTools {

    static class ConceptTools {
        @Tool(name = "create_concept", description = "Create a movie concept document with title, genre, and logline")
        public Map<String, Object> createConcept(String title, String genre, String logline) {
            return Map.of("concept", Map.of(
                "title", title,
                "genre", genre,
                "logline", logline,
                "status", "approved"
            ));
        }
    }

    static class ScriptTools {
        @Tool(name = "write_scene", description = "Write a single scene for the script with location, action, and optional dialogue")
        public Map<String, Object> writeScene(int sceneNumber, String location, String action, String dialogue) {
            java.util.Map<String, Object> scene = new java.util.LinkedHashMap<>();
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
        @Tool(name = "describe_visual", description = "Describe visual direction for a scene: shot type and visual description")
        public Map<String, Object> describeVisual(int sceneNumber, String shotType, String description) {
            return Map.of("visual", Map.of(
                "scene", sceneNumber,
                "shot_type", shotType,
                "description", description
            ));
        }
    }

    static class AudioTools {
        @Tool(name = "specify_audio", description = "Specify audio direction for a scene: music mood and sound effects")
        public Map<String, Object> specifyAudio(int sceneNumber, String musicMood, String soundEffects) {
            return Map.of("audio", Map.of(
                "scene", sceneNumber,
                "music_mood", musicMood,
                "sound_effects", soundEffects
            ));
        }
    }

    static class ProducerTools {
        @Tool(name = "assemble_production", description = "Assemble final production notes with title, scene count, and estimated runtime")
        public Map<String, Object> assembleProduction(String title, int totalScenes, String estimatedRuntime) {
            return Map.of("production", Map.of(
                "title", title,
                "total_scenes", totalScenes,
                "estimated_runtime", estimatedRuntime,
                "status", "ready_for_production"
            ));
        }
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) {
        List<ToolDef> conceptTools = ToolRegistry.fromInstance(new ConceptTools());
        List<ToolDef> rawScriptTools = ToolRegistry.fromInstance(new ScriptTools());
        // Python's write_scene has dialogue with a default "" — only first 3 params required
        ToolDef rawWriteScene = rawScriptTools.get(0);
        Map<String, Object> wsSchema = new java.util.LinkedHashMap<>((Map<String, Object>) rawWriteScene.getInputSchema());
        wsSchema.put("required", java.util.List.of("scene_number", "location", "action"));
        ToolDef writeSceneTool = ToolDef.builder()
            .name(rawWriteScene.getName()).description(rawWriteScene.getDescription())
            .inputSchema(wsSchema).outputSchema(rawWriteScene.getOutputSchema())
            .toolType(rawWriteScene.getToolType()).func(rawWriteScene.getFunc())
            .build();
        List<ToolDef> scriptTools = new java.util.ArrayList<>(rawScriptTools);
        scriptTools.set(0, writeSceneTool);
        List<ToolDef> visualTools = ToolRegistry.fromInstance(new VisualTools());
        List<ToolDef> audioTools = ToolRegistry.fromInstance(new AudioTools());
        List<ToolDef> producerTools = ToolRegistry.fromInstance(new ProducerTools());

        Agent conceptDeveloper = Agent.builder()
            .name("concept_developer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a creative director. Develop a concept for a short film "
                + "based on the given theme. Use create_concept to document the "
                + "title, genre, and logline. Keep it concise and compelling.")
            .tools(conceptTools)
            .build();

        Agent scriptwriter = Agent.builder()
            .name("scriptwriter")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a scriptwriter. Based on the concept from the previous "
                + "stage, write 3 short scenes using write_scene for each. "
                + "Include location, action, and brief dialogue.")
            .tools(scriptTools)
            .build();

        Agent visualDirector = Agent.builder()
            .name("visual_director")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a visual director. For each scene written by the "
                + "scriptwriter, use describe_visual to specify camera shots, "
                + "lighting, and visual mood. Create one visual spec per scene.")
            .tools(visualTools)
            .build();

        Agent audioDesigner = Agent.builder()
            .name("audio_designer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are an audio designer. For each scene, use specify_audio "
                + "to define the music mood and key sound effects. Match the "
                + "audio to the visual mood described by the visual director.")
            .tools(audioTools)
            .build();

        Agent producer = Agent.builder()
            .name("producer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are the producer. Review all previous stages and use "
                + "assemble_production to create final production notes. "
                + "Summarize the complete short film with all creative elements.")
            .tools(producerTools)
            .build();

        // Full pipeline: concept → script → visuals → audio → assembly
        Agent pipeline = Agent.builder()
            .name("movie_production_pipeline")
            .model(Settings.LLM_MODEL)
            .agents(conceptDeveloper, scriptwriter, visualDirector, audioDesigner, producer)
            .strategy(Strategy.SEQUENTIAL)
            .build();

        AgentResult result = Agentspan.run(pipeline,
            "Create a 3-scene short film about a robot discovering music "
            + "for the first time in a post-apocalyptic world.");
        result.printResult();

        Agentspan.shutdown();
    }
}
