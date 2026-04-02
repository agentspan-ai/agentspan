/**
 * 40 - Media Generation Agent
 *
 * Demonstrates Conductor's built-in media generation system tasks
 * (GENERATE_IMAGE, GENERATE_AUDIO, GENERATE_VIDEO) exposed as native agent
 * tools via imageTool(), audioTool(), and videoTool(). These are server-side
 * tools -- no worker process is needed.
 *
 * Architecture:
 *   orchestrator agent
 *     tools: generate_image  (DALL-E 3)
 *            text_to_speech  (OpenAI TTS)
 *            generate_video  (OpenAI Sora)
 *
 * Requirements:
 *   - Conductor server with OpenAI integration configured
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, imageTool, audioTool, videoTool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Media generation tools (server-side, no worker needed) -------------------

const genImage = imageTool({
  name: 'generate_image',
  description: 'Generate an image from a text description using DALL-E 3.',
  llmProvider: 'openai',
  model: 'dall-e-3',
});

const genAudio = audioTool({
  name: 'text_to_speech',
  description: 'Convert text to natural-sounding speech audio using OpenAI TTS.',
  llmProvider: 'openai',
  model: 'tts-1',
});

const genVideo = videoTool({
  name: 'generate_video',
  description: 'Generate a short video clip from a text description using OpenAI Sora.',
  llmProvider: 'openai',
  model: 'sora-2',
  resolution: '1280x720',
});

// -- Orchestrator Agent -------------------------------------------------------

export const mediaAgent = new Agent({
  name: 'media_generator',
  model: llmModel,
  tools: [genImage, genAudio, genVideo],
  instructions:
    'You are a creative media generation assistant. You can generate:\n\n' +
    '1. **Images** -- from text descriptions using DALL-E 3.\n' +
    '2. **Audio** -- text-to-speech using OpenAI TTS ' +
    '(voices: alloy, echo, fable, onyx, nova, shimmer).\n' +
    '3. **Video** -- short video clips from text using OpenAI Sora.\n\n' +
    'IMPORTANT: Image prompts MUST be under 950 characters.\n' +
    'Call the appropriate tool once and present the result.',
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('Media Generation Agent');
    console.log('='.repeat(60));
    const result = await runtime.run(
    mediaAgent,
    'Create an image of a serene Japanese garden with a koi pond ' +
    'at sunset, cherry blossoms falling gently. Use vivid style. ' +
    'Use that image to generate a video with audio narration describing the image.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(mediaAgent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents media_generator
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(mediaAgent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('40-media-generation-agent.ts') || process.argv[1]?.endsWith('40-media-generation-agent.js')) {
  main().catch(console.error);
}
