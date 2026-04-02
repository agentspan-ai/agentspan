/**
 * Multimodal Agent -- analyze images and video with vision-capable models.
 *
 * Demonstrates multimodal input via the `media` option on
 * `runtime.run()`.  Pass image or video URLs alongside your text prompt --
 * the Conductor server includes them in the ChatMessage `media` field,
 * enabling vision-capable models (GPT-4o, Gemini, Claude) to see them.
 *
 * Supported media types:
 *   - Images: JPEG, PNG, GIF, WebP (URL or data URI)
 *   - Video: MP4, MOV (provider-dependent, e.g. Gemini)
 *   - Audio: MP3, WAV (provider-dependent)
 *
 * Requirements:
 *   - Conductor server with LLM support (OpenAI key configured)
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Example 1: Simple image analysis --------------------------------------

export const visionAgent = new Agent({
  name: 'vision_analyst',
  model: llmModel,
  instructions:
    'You are a visual analysis expert. Describe images in detail, ' +
    'noting composition, colors, subjects, and any text visible.',
});

// -- Example 2: Image analysis with tools ----------------------------------

const searchSimilar = tool(
  async (args: { description: string }) => {
    return `Found 3 similar images matching: '${args.description}'`;
  },
  {
    name: 'search_similar',
    description: 'Search for similar images based on a description.',
    inputSchema: {
      type: 'object',
      properties: {
        description: { type: 'string', description: 'Description to search for' },
      },
      required: ['description'],
    },
  },
);

const saveAnalysis = tool(
  async (args: { title: string; analysis: string }) => {
    return `Saved analysis '${args.title}': ${args.analysis.slice(0, 100)}...`;
  },
  {
    name: 'save_analysis',
    description: 'Save an image analysis report.',
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Title of the analysis' },
        analysis: { type: 'string', description: 'The analysis content' },
      },
      required: ['title', 'analysis'],
    },
  },
);

export const visionWithTools = new Agent({
  name: 'vision_researcher',
  model: llmModel,
  instructions:
    'You are a visual research assistant. Analyze images, search for ' +
    'similar ones, and save your findings. Always save your analysis.',
  tools: [searchSimilar, saveAnalysis],
});

// -- Example 3: Multi-image comparison -------------------------------------

export const comparator = new Agent({
  name: 'image_comparator',
  model: llmModel,
  instructions:
    'You are an image comparison specialist. When given multiple images, ' +
    'compare and contrast them in detail: similarities, differences, ' +
    'style, composition, and subject matter.',
});

// -- Example 4: Multi-agent pipeline with vision ---------------------------
// First agent describes the image, second generates a creative story

export const describer = new Agent({
  name: 'describer',
  model: llmModel,
  instructions: 'Describe the image in 2-3 vivid sentences.',
});

export const storyteller = new Agent({
  name: 'storyteller',
  model: llmModel,
  instructions:
    'You receive an image description. Write a short creative ' +
    'story (3-4 sentences) inspired by it.',
});

const creativePipeline = describer.pipe(storyteller);

// -- Run -------------------------------------------------------------------

// Sample public-domain images for demonstration
const SAMPLE_IMAGE = 'https://orkes.io/Home-Page-Prompt-to-Workflow-1.png';
const SAMPLE_IMAGE_2 = 'https://orkes.io/icons/hero-section-workflow_updated.png';

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // --- 1. Single image analysis ---
    console.log('=== Single Image Analysis ===');
    const result1 = await runtime.run(
    visionAgent,
    'What do you see in this image? Describe it in detail.',
    { media: [SAMPLE_IMAGE] },
    );
    result1.printResult();

    // --- 2. Image analysis with tools ---
    console.log('\n=== Image Analysis with Tools ===');
    const result2 = await runtime.run(
    visionWithTools,
    'Analyze this image, search for similar ones, and save your findings.',
    { media: [SAMPLE_IMAGE] },
    );
    result2.printResult();

    // --- 3. Compare multiple images ---
    console.log('\n=== Multi-Image Comparison ===');
    const result3 = await runtime.run(
    comparator,
    'Compare these two images. What are the key differences?',
    { media: [SAMPLE_IMAGE, SAMPLE_IMAGE_2] },
    );
    result3.printResult();

    // --- 4. Creative pipeline from image ---
    console.log('\n=== Creative Pipeline (describe -> story) ===');
    const result4 = await runtime.run(
    creativePipeline,
    'Create a story inspired by this image.',
    { media: [SAMPLE_IMAGE_2] },
    );
    result4.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(visionAgent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents vision_analyst
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(visionAgent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('30-multimodal-agent.ts') || process.argv[1]?.endsWith('30-multimodal-agent.js')) {
  main().catch(console.error);
}
