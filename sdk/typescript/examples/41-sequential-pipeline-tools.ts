/**
 * 41 - Sequential Pipeline with Stage-Level Tools
 *
 * Demonstrates the sequential strategy where EACH sub-agent in the pipeline
 * has its own tools for producing structured output. Each stage builds on
 * the previous one's output:
 *
 *   conceptDeveloper >> scriptwriter >> visualDirector >> audioDesigner >> producer
 *
 * This shows how to give individual pipeline agents their own tools while
 * composing them into an ordered sequence using the .pipe() method.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// -- Stage tools --------------------------------------------------------------

const createConcept = tool(
  async (args: { title: string; genre: string; logline: string }) => {
    return {
      concept: {
        title: args.title,
        genre: args.genre,
        logline: args.logline,
        status: 'approved',
      },
    };
  },
  {
    name: 'create_concept',
    description: 'Create a movie concept document.',
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Working title for the short film' },
        genre: { type: 'string', description: 'Genre (e.g., sci-fi, drama, comedy)' },
        logline: { type: 'string', description: 'One-sentence summary of the story' },
      },
      required: ['title', 'genre', 'logline'],
    },
  },
);

const writeScene = tool(
  async (args: {
    sceneNumber: number;
    location: string;
    action: string;
    dialogue?: string;
  }) => {
    const scene: Record<string, unknown> = {
      scene: args.sceneNumber,
      location: args.location,
      action: args.action,
    };
    if (args.dialogue) {
      scene.dialogue = args.dialogue;
    }
    return { scene };
  },
  {
    name: 'write_scene',
    description: 'Write a single scene for the script.',
    inputSchema: {
      type: 'object',
      properties: {
        sceneNumber: { type: 'number', description: 'Scene number in sequence' },
        location: { type: 'string', description: 'Scene location description' },
        action: { type: 'string', description: 'Action/direction description' },
        dialogue: { type: 'string', description: 'Optional dialogue for the scene' },
      },
      required: ['sceneNumber', 'location', 'action'],
    },
  },
);

const describeVisual = tool(
  async (args: { sceneNumber: number; shotType: string; description: string }) => {
    return {
      visual: {
        scene: args.sceneNumber,
        shot_type: args.shotType,
        description: args.description,
      },
    };
  },
  {
    name: 'describe_visual',
    description: 'Describe visual direction for a scene.',
    inputSchema: {
      type: 'object',
      properties: {
        sceneNumber: { type: 'number', description: 'Which scene this visual is for' },
        shotType: { type: 'string', description: 'Camera shot type (wide, close-up, tracking, etc.)' },
        description: { type: 'string', description: 'Visual description including lighting, color, mood' },
      },
      required: ['sceneNumber', 'shotType', 'description'],
    },
  },
);

const specifyAudio = tool(
  async (args: { sceneNumber: number; musicMood: string; soundEffects: string }) => {
    return {
      audio: {
        scene: args.sceneNumber,
        music_mood: args.musicMood,
        sound_effects: args.soundEffects,
      },
    };
  },
  {
    name: 'specify_audio',
    description: 'Specify audio direction for a scene.',
    inputSchema: {
      type: 'object',
      properties: {
        sceneNumber: { type: 'number', description: 'Which scene this audio is for' },
        musicMood: { type: 'string', description: 'Music mood/style description' },
        soundEffects: { type: 'string', description: 'Key sound effects needed' },
      },
      required: ['sceneNumber', 'musicMood', 'soundEffects'],
    },
  },
);

const assembleProduction = tool(
  async (args: { title: string; totalScenes: number; estimatedRuntime: string }) => {
    return {
      production: {
        title: args.title,
        total_scenes: args.totalScenes,
        estimated_runtime: args.estimatedRuntime,
        status: 'ready_for_production',
      },
    };
  },
  {
    name: 'assemble_production',
    description: 'Assemble final production notes.',
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Final title of the short film' },
        totalScenes: { type: 'number', description: 'Number of scenes in the final cut' },
        estimatedRuntime: { type: 'string', description: 'Estimated runtime (e.g., "3 minutes")' },
      },
      required: ['title', 'totalScenes', 'estimatedRuntime'],
    },
  },
);

// -- Pipeline stages ----------------------------------------------------------

export const conceptDeveloper = new Agent({
  name: 'concept_developer',
  model: llmModel,
  instructions:
    'You are a creative director. Develop a concept for a short film ' +
    'based on the given theme. Use create_concept to document the ' +
    'title, genre, and logline. Keep it concise and compelling.',
  tools: [createConcept],
});

export const scriptwriter = new Agent({
  name: 'scriptwriter',
  model: llmModel,
  instructions:
    'You are a scriptwriter. Based on the concept from the previous ' +
    'stage, write 3 short scenes using write_scene for each. ' +
    'Include location, action, and brief dialogue.',
  tools: [writeScene],
});

export const visualDirector = new Agent({
  name: 'visual_director',
  model: llmModel,
  instructions:
    'You are a visual director. For each scene written by the ' +
    'scriptwriter, use describe_visual to specify camera shots, ' +
    'lighting, and visual mood. Create one visual spec per scene.',
  tools: [describeVisual],
});

export const audioDesigner = new Agent({
  name: 'audio_designer',
  model: llmModel,
  instructions:
    'You are an audio designer. For each scene, use specify_audio ' +
    'to define the music mood and key sound effects. Match the ' +
    'audio to the visual mood described by the visual director.',
  tools: [specifyAudio],
});

export const producer = new Agent({
  name: 'producer',
  model: llmModel,
  instructions:
    'You are the producer. Review all previous stages and use ' +
    'assemble_production to create final production notes. ' +
    'Summarize the complete short film with all creative elements.',
  tools: [assembleProduction],
});

// Full pipeline: concept -> script -> visuals -> audio -> assembly
const pipeline = conceptDeveloper
  .pipe(scriptwriter)
  .pipe(visualDirector)
  .pipe(audioDesigner)
  .pipe(producer);

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    pipeline,
    'Create a 3-scene short film about a robot discovering music ' +
    'for the first time in a post-apocalyptic world.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(pipeline);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents concept_developer
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(pipeline);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
