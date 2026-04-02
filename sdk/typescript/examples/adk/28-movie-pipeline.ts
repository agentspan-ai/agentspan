/**
 * Short Movie Pipeline -- sequential content generation stages.
 *
 * Demonstrates:
 *   - SequentialAgent with 5 specialized stages
 *   - Each stage builds on previous output (concept -> script -> visuals -> audio -> assembly)
 *   - Tools at each stage for structured output
 *
 * Inspired by the Google ADK short-movie-agents sample which uses
 * a multi-stage pipeline for creative content production.
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, SequentialAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Stage tools ──────────────────────────────────────────────────────

const createConcept = new FunctionTool({
  name: 'create_concept',
  description: 'Create a movie concept document.',
  parameters: z.object({
    title: z.string().describe('Working title for the short film'),
    genre: z.string().describe('Genre (e.g., sci-fi, drama, comedy)'),
    logline: z.string().describe('One-sentence summary of the story'),
  }),
  execute: async (args: { title: string; genre: string; logline: string }) => ({
    concept: {
      title: args.title,
      genre: args.genre,
      logline: args.logline,
      status: 'approved',
    },
  }),
});

const writeScene = new FunctionTool({
  name: 'write_scene',
  description: 'Write a single scene for the script.',
  parameters: z.object({
    scene_number: z.number().describe('Scene number in sequence'),
    location: z.string().describe('Scene location description'),
    action: z.string().describe('Action/direction description'),
    dialogue: z.string().describe('Optional dialogue for the scene').default(''),
  }),
  execute: async (args: {
    scene_number: number;
    location: string;
    action: string;
    dialogue?: string;
  }) => {
    const scene: Record<string, unknown> = {
      scene: args.scene_number,
      location: args.location,
      action: args.action,
    };
    if (args.dialogue) {
      scene.dialogue = args.dialogue;
    }
    return { scene };
  },
});

const describeVisual = new FunctionTool({
  name: 'describe_visual',
  description: 'Describe visual direction for a scene.',
  parameters: z.object({
    scene_number: z.number().describe('Which scene this visual is for'),
    shot_type: z.string().describe('Camera shot type (wide, close-up, tracking, etc.)'),
    description: z
      .string()
      .describe('Visual description including lighting, color, mood'),
  }),
  execute: async (args: {
    scene_number: number;
    shot_type: string;
    description: string;
  }) => ({
    visual: {
      scene: args.scene_number,
      shot_type: args.shot_type,
      description: args.description,
    },
  }),
});

const specifyAudio = new FunctionTool({
  name: 'specify_audio',
  description: 'Specify audio direction for a scene.',
  parameters: z.object({
    scene_number: z.number().describe('Which scene this audio is for'),
    music_mood: z.string().describe('Music mood/style description'),
    sound_effects: z.string().describe('Key sound effects needed'),
  }),
  execute: async (args: {
    scene_number: number;
    music_mood: string;
    sound_effects: string;
  }) => ({
    audio: {
      scene: args.scene_number,
      music_mood: args.music_mood,
      sound_effects: args.sound_effects,
    },
  }),
});

const assembleProduction = new FunctionTool({
  name: 'assemble_production',
  description: 'Assemble final production notes.',
  parameters: z.object({
    title: z.string().describe('Final title of the short film'),
    total_scenes: z.number().describe('Number of scenes in the final cut'),
    estimated_runtime: z.string().describe('Estimated runtime (e.g., "3 minutes")'),
  }),
  execute: async (args: {
    title: string;
    total_scenes: number;
    estimated_runtime: string;
  }) => ({
    production: {
      title: args.title,
      total_scenes: args.total_scenes,
      estimated_runtime: args.estimated_runtime,
      status: 'ready_for_production',
    },
  }),
});

// ── Pipeline stages ──────────────────────────────────────────────────

export const conceptDeveloper = new LlmAgent({
  name: 'concept_developer',
  model,
  instruction:
    'You are a creative director. Develop a concept for a short film ' +
    'based on the given theme. Use create_concept to document the ' +
    'title, genre, and logline. Keep it concise and compelling.',
  tools: [createConcept],
});

export const scriptwriter = new LlmAgent({
  name: 'scriptwriter',
  model,
  instruction:
    'You are a scriptwriter. Based on the concept from the previous ' +
    'stage, write 3 short scenes using write_scene for each. ' +
    'Include location, action, and brief dialogue.',
  tools: [writeScene],
});

export const visualDirector = new LlmAgent({
  name: 'visual_director',
  model,
  instruction:
    'You are a visual director. For each scene written by the ' +
    'scriptwriter, use describe_visual to specify camera shots, ' +
    'lighting, and visual mood. Create one visual spec per scene.',
  tools: [describeVisual],
});

export const audioDesigner = new LlmAgent({
  name: 'audio_designer',
  model,
  instruction:
    'You are an audio designer. For each scene, use specify_audio ' +
    'to define the music mood and key sound effects. Match the ' +
    'audio to the visual mood described by the visual director.',
  tools: [specifyAudio],
});

export const producer = new LlmAgent({
  name: 'producer',
  model,
  instruction:
    'You are the producer. Review all previous stages and use ' +
    'assemble_production to create final production notes. ' +
    'Summarize the complete short film with all creative elements.',
  tools: [assembleProduction],
});

// Full pipeline: concept -> script -> visuals -> audio -> assembly
export const moviePipeline = new SequentialAgent({
  name: 'short_movie_pipeline',
  subAgents: [conceptDeveloper, scriptwriter, visualDirector, audioDesigner, producer],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    moviePipeline,
    'Create a 3-scene short film about a robot discovering music ' +
    'for the first time in a post-apocalyptic world.',
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(moviePipeline);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents short_movie_pipeline
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(moviePipeline);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('28-movie-pipeline.ts') || process.argv[1]?.endsWith('28-movie-pipeline.js')) {
  main().catch(console.error);
}
