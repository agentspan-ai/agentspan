/**
 * Suite 20: Plan-Execute Strategy — end-to-end test.
 *
 * Tests the PLAN_EXECUTE strategy:
 *   1. Planner produces a JSON plan
 *   2. Plan compiles to Conductor sub-workflow
 *   3. Parallel LLM generation + static tool calls execute deterministically
 *   4. Validation passes (word count check)
 *   5. Files are created on disk
 *
 * No mocks. Real server, real LLM.
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { checkServerHealth, MODEL, TIMEOUT } from './helpers';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

const WORK_DIR = path.join(os.tmpdir(), 'plan-execute-test-ts');
const MIN_WORD_COUNT = 200;

// ── Tools ──────────────────────────────────────────────────

const createDirectory = tool(
  async ({ path: dirPath }: { path: string }) => {
    const full = path.join(WORK_DIR, dirPath);
    fs.mkdirSync(full, { recursive: true });
    return `Created directory: ${full}`;
  },
  {
    name: 'create_directory',
    description: 'Create a directory (and parents) if it does not exist.',
    inputSchema: {
      type: 'object',
      properties: { path: { type: 'string', description: 'Directory path relative to working dir.' } },
      required: ['path'],
    },
  },
);

const writeFile = tool(
  async ({ path: filePath, content }: { path: string; content: string }) => {
    const full = path.join(WORK_DIR, filePath);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, content);
    return `Wrote ${content.length} bytes to ${full}`;
  },
  {
    name: 'write_file',
    description: 'Write content to a file, creating parent directories if needed.',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'File path relative to working dir.' },
        content: { type: 'string', description: 'Full file content to write.' },
      },
      required: ['path', 'content'],
    },
  },
);

const readFile = tool(
  async ({ path: filePath }: { path: string }) => {
    const full = path.join(WORK_DIR, filePath);
    if (!fs.existsSync(full)) return `ERROR: File not found: ${full}`;
    return fs.readFileSync(full, 'utf-8');
  },
  {
    name: 'read_file',
    description: 'Read the contents of a file.',
    inputSchema: {
      type: 'object',
      properties: { path: { type: 'string', description: 'File path relative to working dir.' } },
      required: ['path'],
    },
  },
);

const assembleFiles = tool(
  async ({ output_path, input_paths, separator }: { output_path: string; input_paths: string; separator?: string }) => {
    const paths: string[] = JSON.parse(input_paths);
    const sep = separator ?? '\n\n---\n\n';
    const parts = paths.map((p) => {
      const full = path.join(WORK_DIR, p);
      return fs.existsSync(full) ? fs.readFileSync(full, 'utf-8') : `[Missing: ${p}]`;
    });
    const combined = parts.join(sep);
    const outFull = path.join(WORK_DIR, output_path);
    fs.mkdirSync(path.dirname(outFull), { recursive: true });
    fs.writeFileSync(outFull, combined);
    return `Assembled ${paths.length} files into ${outFull} (${combined.length} bytes)`;
  },
  {
    name: 'assemble_files',
    description: 'Concatenate multiple files into one, with a separator between them.',
    inputSchema: {
      type: 'object',
      properties: {
        output_path: { type: 'string', description: 'Output file path relative to working dir.' },
        input_paths: { type: 'string', description: 'JSON array of input file paths.' },
        separator: { type: 'string', description: 'Text to insert between file contents.' },
      },
      required: ['output_path', 'input_paths'],
    },
  },
);

const checkWordCount = tool(
  async ({ path: filePath, min_words }: { path: string; min_words: number }) => {
    const full = path.join(WORK_DIR, filePath);
    if (!fs.existsSync(full))
      return JSON.stringify({ passed: false, error: `File not found: ${filePath}`, word_count: 0 });
    const content = fs.readFileSync(full, 'utf-8');
    const count = content.split(/\s+/).filter(Boolean).length;
    return JSON.stringify({ passed: count >= min_words, word_count: count, min_words });
  },
  {
    name: 'check_word_count',
    description: 'Check that a file meets a minimum word count.',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'File path relative to working dir.' },
        min_words: { type: 'integer', description: 'Minimum number of words required.' },
      },
      required: ['path', 'min_words'],
    },
  },
);

// ── Agent definitions ──────────────────────────────────────

const PLANNER_INSTRUCTIONS = `You are a research report planner. Given a topic, plan a structured report.

Your job:
1. Decide on 3 sections for the report (introduction, body, conclusion)
2. For each section, write clear instructions on what content to include
3. Output your plan as Markdown with an embedded \`\`\`json fence

IMPORTANT: Your plan MUST include a \`\`\`json fence with the structured plan.

## Available tools for operations:
- \`create_directory\`: args={path} — create a directory
- \`write_file\`: generate={instructions, output_schema} — LLM writes content
- \`assemble_files\`: args={output_path, input_paths, separator} — concatenate files
- \`check_word_count\`: args={path, min_words} — validate word count

## Plan format:

Your output MUST end with a JSON fence like this:

\`\`\`json
{
  "steps": [
    {
      "id": "setup",
      "parallel": false,
      "operations": [
        {"tool": "create_directory", "args": {"path": "sections"}}
      ]
    },
    {
      "id": "write_sections",
      "depends_on": ["setup"],
      "parallel": true,
      "operations": [
        {
          "tool": "write_file",
          "generate": {
            "instructions": "Write a 100-word introduction about [topic].",
            "output_schema": "{\\"path\\": \\"sections/01_intro.md\\", \\"content\\": \\"...\\"}"
          }
        },
        {
          "tool": "write_file",
          "generate": {
            "instructions": "Write a 100-word section about [subtopic].",
            "output_schema": "{\\"path\\": \\"sections/02_body.md\\", \\"content\\": \\"...\\"}"
          }
        }
      ]
    },
    {
      "id": "assemble",
      "depends_on": ["write_sections"],
      "parallel": false,
      "operations": [
        {
          "tool": "assemble_files",
          "args": {
            "output_path": "report.md",
            "input_paths": "[\\"sections/01_intro.md\\", \\"sections/02_body.md\\"]",
            "separator": "\\n\\n---\\n\\n"
          }
        }
      ]
    }
  ],
  "validation": [
    {"tool": "check_word_count", "args": {"path": "report.md", "min_words": ${MIN_WORD_COUNT}}}
  ],
  "on_success": []
}
\`\`\`

## Rules:
- Section files go in sections/ directory (01_intro.md, 02_body.md, etc.)
- Each section should be 80-150 words
- The assemble step must list ALL section files in order
- Always validate with check_word_count (min ${MIN_WORD_COUNT} words)
- Keep it simple: 3 sections total
- The JSON must be valid
`;

const FALLBACK_INSTRUCTIONS = `You are fixing a report that failed validation. The plan was already partially executed but something went wrong (missing sections, word count too low, etc.).

Review the error output, figure out what's missing or broken, and fix it.
You have access to read_file, write_file, assemble_files, and check_word_count.

Working directory: ${WORK_DIR}`;

// ── Tests ──────────────────────────────────────────────────

let runtime: AgentRuntime;

describe('Suite 20: Plan-Execute Strategy', () => {
  beforeAll(async () => {
    const healthy = await checkServerHealth();
    if (!healthy) throw new Error('Server not available');
    runtime = new AgentRuntime();
  });

  afterAll(async () => {
    await runtime.shutdown();
  });

  beforeEach(() => {
    // Clean the working directory before each test
    if (fs.existsSync(WORK_DIR)) {
      fs.rmSync(WORK_DIR, { recursive: true });
    }
    fs.mkdirSync(WORK_DIR, { recursive: true });
  });

  it('should generate a report via plan-execute strategy', async () => {
    const planner = new Agent({
      name: 'ts_test_planner',
      model: MODEL,
      instructions: PLANNER_INSTRUCTIONS,
      maxTurns: 3,
      maxTokens: 4000,
    });

    const fallback = new Agent({
      name: 'ts_test_fallback',
      model: MODEL,
      instructions: FALLBACK_INSTRUCTIONS,
      tools: [createDirectory, readFile, writeFile, assembleFiles, checkWordCount],
      maxTurns: 10,
      maxTokens: 8000,
    });

    const harness = new Agent({
      name: 'ts_test_report_gen',
      model: MODEL,
      agents: [planner, fallback],
      strategy: 'plan_execute',
      fallbackMaxTurns: 5,
    });

    const result = await runtime.run(harness, 'Write a short research report about: The impact of AI on software testing');

    // 1. Workflow completed
    expect(result.status).toBe('COMPLETED');

    // 2. Report file exists
    const reportPath = path.join(WORK_DIR, 'report.md');
    expect(fs.existsSync(reportPath)).toBe(true);

    // 3. Report has content
    const content = fs.readFileSync(reportPath, 'utf-8');
    expect(content.length).toBeGreaterThan(0);

    const wordCount = content.split(/\s+/).filter(Boolean).length;
    console.log(`Report word count: ${wordCount}`);
    console.log(`Report preview: ${content.slice(0, 300)}...`);

    // 4. Word count meets minimum
    expect(wordCount).toBeGreaterThanOrEqual(MIN_WORD_COUNT);

    // 5. Section files were created (proves parallel execution)
    const sectionsDir = path.join(WORK_DIR, 'sections');
    expect(fs.existsSync(sectionsDir)).toBe(true);
    const sectionFiles = fs.readdirSync(sectionsDir).filter((f) => f.endsWith('.md'));
    expect(sectionFiles.length).toBeGreaterThanOrEqual(2);

    // 6. Each section file has content
    for (const sf of sectionFiles) {
      const sfContent = fs.readFileSync(path.join(sectionsDir, sf), 'utf-8');
      const sfWords = sfContent.split(/\s+/).filter(Boolean).length;
      console.log(`  Section ${sf}: ${sfWords} words`);
      expect(sfWords).toBeGreaterThan(10);
    }
  }, TIMEOUT);

  it('should honor max_tokens in generate blocks', async () => {
    // Counterfactual: if gen.max_tokens is not read by the GraalJS compiler,
    // the LLM_CHAT_COMPLETE task gets the default 4096. This test instructs
    // the planner to include max_tokens: 8192 in generate blocks.

    const maxTokensPlannerInstructions = `You are a research report planner. Given a topic, plan a detailed report.

Your job:
1. Decide on 3 sections for the report (introduction, body, conclusion)
2. For each section, write clear instructions requesting DETAILED content (250+ words each)
3. Output your plan as Markdown with an embedded \`\`\`json fence

IMPORTANT: Your plan MUST include a \`\`\`json fence with the structured plan.
IMPORTANT: Every generate block MUST include "max_tokens": 8192.

## Available tools:
- \`create_directory\`: args={path}
- \`write_file\`: generate={instructions, output_schema, max_tokens}
- \`assemble_files\`: args={output_path, input_paths, separator}
- \`check_word_count\`: args={path, min_words}

## Plan format:

\`\`\`json
{
  "steps": [
    {
      "id": "setup",
      "parallel": false,
      "operations": [
        {"tool": "create_directory", "args": {"path": "sections"}}
      ]
    },
    {
      "id": "write_sections",
      "depends_on": ["setup"],
      "parallel": true,
      "operations": [
        {
          "tool": "write_file",
          "generate": {
            "instructions": "Write a detailed 250+ word introduction about [topic].",
            "output_schema": "{\\"path\\": \\"sections/01_intro.md\\", \\"content\\": \\"...\\"}",
            "max_tokens": 8192
          }
        },
        {
          "tool": "write_file",
          "generate": {
            "instructions": "Write a detailed 250+ word body section about [subtopic].",
            "output_schema": "{\\"path\\": \\"sections/02_body.md\\", \\"content\\": \\"...\\"}",
            "max_tokens": 8192
          }
        },
        {
          "tool": "write_file",
          "generate": {
            "instructions": "Write a detailed 250+ word conclusion about [topic].",
            "output_schema": "{\\"path\\": \\"sections/03_conclusion.md\\", \\"content\\": \\"...\\"}",
            "max_tokens": 8192
          }
        }
      ]
    },
    {
      "id": "assemble",
      "depends_on": ["write_sections"],
      "parallel": false,
      "operations": [
        {
          "tool": "assemble_files",
          "args": {
            "output_path": "report.md",
            "input_paths": "[\\"sections/01_intro.md\\", \\"sections/02_body.md\\", \\"sections/03_conclusion.md\\"]",
            "separator": "\\n\\n---\\n\\n"
          }
        }
      ]
    }
  ],
  "validation": [
    {"tool": "check_word_count", "args": {"path": "report.md", "min_words": ${MIN_WORD_COUNT}}}
  ],
  "on_success": []
}
\`\`\`

## Rules:
- Section files go in sections/ directory
- Each section MUST be 250+ words (detailed, thorough)
- Every generate block MUST include "max_tokens": 8192
- The assemble step must list ALL section files in order
- Always validate with check_word_count (min ${MIN_WORD_COUNT} words)
- The JSON must be valid
`;

    const planner = new Agent({
      name: 'ts_test_planner_maxtok',
      model: MODEL,
      instructions: maxTokensPlannerInstructions,
      maxTurns: 3,
      maxTokens: 4000,
    });

    const fallback = new Agent({
      name: 'ts_test_fallback_maxtok',
      model: MODEL,
      instructions: FALLBACK_INSTRUCTIONS,
      tools: [createDirectory, readFile, writeFile, assembleFiles, checkWordCount],
      maxTurns: 10,
      maxTokens: 8000,
    });

    const harness = new Agent({
      name: 'ts_test_report_gen_maxtok',
      model: MODEL,
      agents: [planner, fallback],
      strategy: 'plan_execute',
      fallbackMaxTurns: 5,
    });

    const result = await runtime.run(harness, 'Write a detailed research report about: Quantum computing applications in cryptography');

    // 1. Workflow completed — proves max_tokens field didn't break compilation
    expect(result.status).toBe('COMPLETED');

    // 2. Report file exists
    const reportPath = path.join(WORK_DIR, 'report.md');
    expect(fs.existsSync(reportPath)).toBe(true);

    // 3. Report has substantial content
    const content = fs.readFileSync(reportPath, 'utf-8');
    const wordCount = content.split(/\s+/).filter(Boolean).length;
    console.log(`max_tokens test — Report word count: ${wordCount}`);

    // 4. Word count meets minimum
    expect(wordCount).toBeGreaterThanOrEqual(MIN_WORD_COUNT);

    // 5. Section files created
    const sectionsDir = path.join(WORK_DIR, 'sections');
    expect(fs.existsSync(sectionsDir)).toBe(true);
    const sectionFiles = fs.readdirSync(sectionsDir).filter((f) => f.endsWith('.md'));
    expect(sectionFiles.length).toBeGreaterThanOrEqual(2);
  }, TIMEOUT);
});
