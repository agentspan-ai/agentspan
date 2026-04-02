/**
 * Code Agent -- createReactAgent with write_code, explain_code, and fix_bug tools.
 *
 * Demonstrates:
 *   - Domain-specific tools that return realistic, formatted code strings
 *   - Building a coding assistant that can write, explain, and fix code
 *   - Multi-step tool usage: write then explain, or analyze then fix
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const writeCodeTool = new DynamicStructuredTool({
  name: 'write_code',
  description:
    'Generate code based on a description in the specified programming language.',
  schema: z.object({
    description: z.string().describe('What the code should do'),
    language: z
      .string()
      .optional()
      .describe('The programming language (python, javascript, java, etc.)'),
  }),
  func: async ({ description, language }) => {
    const lang = language ?? 'python';
    const templates: Record<string, string> = {
      'binary search': `\
def binary_search(arr: list, target: int) -> int:
    """Search for target in a sorted list. Returns index or -1."""
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
`,
      fibonacci: `\
def fibonacci(n: int) -> list[int]:
    """Return the first n Fibonacci numbers."""
    if n <= 0:
        return []
    seq = [0, 1]
    while len(seq) < n:
        seq.append(seq[-1] + seq[-2])
    return seq[:n]
`,
    };
    const descLower = description.toLowerCase();
    for (const [key, code] of Object.entries(templates)) {
      if (descLower.includes(key)) {
        return `\`\`\`${lang}\n${code}\`\`\``;
      }
    }
    return (
      `\`\`\`${lang}\n` +
      `# TODO: Implement '${description}'\n` +
      `# This is a scaffold — fill in the logic below.\n` +
      `def solution():\n` +
      `    pass\n` +
      `\`\`\``
    );
  },
});

const explainCodeTool = new DynamicStructuredTool({
  name: 'explain_code',
  description: 'Explain what a piece of code does in plain English.',
  schema: z.object({
    code: z.string().describe('The source code snippet to explain'),
  }),
  func: async ({ code }) => {
    if (code.includes('binary_search') || code.toLowerCase().includes('binary search')) {
      return (
        'This code implements binary search: it repeatedly halves a sorted list ' +
        'to find a target value in O(log n) time, returning the index or -1 if not found.'
      );
    }
    if (code.includes('fibonacci')) {
      return (
        'This code generates Fibonacci numbers: starting with 0 and 1, ' +
        'each subsequent number is the sum of the two before it.'
      );
    }
    return (
      'This code defines a function or set of operations. ' +
      'It takes inputs, processes them according to the logic provided, ' +
      'and returns a result. Review the docstring and variable names for details.'
    );
  },
});

const fixBugTool = new DynamicStructuredTool({
  name: 'fix_bug',
  description:
    'Analyze a buggy code snippet and the error it produces, then return the fixed version.',
  schema: z.object({
    code: z.string().describe('The buggy source code'),
    error_message: z
      .string()
      .describe('The error or unexpected behavior description'),
  }),
  func: async ({ code, error_message }) => {
    if (
      error_message.includes('IndexError') ||
      error_message.toLowerCase().includes('index out of range')
    ) {
      return (
        '# BUG FIX: Added bounds checking to prevent IndexError\n' +
        '# Original code had off-by-one error in loop range.\n' +
        code.replace('range(len(arr))', 'range(len(arr) - 1)') +
        '\n# Fixed: adjusted loop range to avoid accessing out-of-bounds index.'
      );
    }
    if (error_message.includes('ZeroDivisionError')) {
      return (
        '# BUG FIX: Added zero-division guard\n' +
        code +
        "\n# Fixed: wrap the division in an 'if denominator != 0' check."
      );
    }
    return (
      '# BUG FIX APPLIED\n' +
      `# Error: ${error_message}\n` +
      code +
      '\n# Review the logic above and add appropriate error handling.'
    );
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const tools = [writeCodeTool, explainCodeTool, fixBugTool];
const graph = createReactAgent({
  llm,
  tools,
  prompt:
    'You are an expert software engineer assistant. ' +
    'Use your tools to write, explain, and debug code. ' +
    'Always provide clear, well-commented solutions.',
});

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langgraph',
};

const PROMPT =
  'Write a binary search function in Python and explain how it works.';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(graph);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents code_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('12-code-agent.ts') || process.argv[1]?.endsWith('12-code-agent.js')) {
  main().catch(console.error);
}
