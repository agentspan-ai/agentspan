/**
 * Code Interpreter -- agent that writes and (safely) evaluates expressions.
 *
 * Demonstrates:
 *   - An agent that generates and explains code
 *   - Safe expression evaluation for numeric calculations
 *   - Code explanation and syntax checking assistance
 *   - Practical use case: interactive coding assistant
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const evaluateExpressionTool = new DynamicStructuredTool({
  name: 'evaluate_expression',
  description:
    'Evaluate a safe arithmetic expression and return the result. ' +
    'Supports +, -, *, /, **, %. No function calls or variables allowed. ' +
    "Example: '(3 + 4) * 2 ** 3'",
  schema: z.object({
    expression: z.string().describe('The arithmetic expression to evaluate'),
  }),
  func: async ({ expression }) => {
    try {
      // Only allow safe arithmetic characters
      const sanitized = expression.replace(/[^0-9+\-*/().% ]/g, '');
      if (sanitized !== expression.replace(/\s+/g, ' ').trim().replace(/\*\*/g, '**')) {
        // Fallback: just use the sanitized version
      }
      const safeExpr = expression.replace(/[^0-9+\-*/().%\s^]/g, '').replace(/\^/g, '**');
      const result = Function(`"use strict"; return (${safeExpr})`)();
      return `${expression} = ${result}`;
    } catch (e) {
      return `Error evaluating '${expression}': ${e}`;
    }
  },
});

const explainCodeTool = new DynamicStructuredTool({
  name: 'explain_code',
  description:
    'Explain what a code snippet does in plain English. Returns a line-by-line explanation.',
  schema: z.object({
    code: z.string().describe('The code snippet to explain'),
  }),
  func: async ({ code }) => {
    const lines = code.trim().split('\n');
    const explanations: string[] = [];
    for (let i = 0; i < lines.length; i++) {
      const stripped = lines[i].trim();
      const lineNum = i + 1;
      if (!stripped || stripped.startsWith('#') || stripped.startsWith('//')) {
        explanations.push(`Line ${lineNum}: (comment or blank)`);
      } else if (stripped.includes('=') && !stripped.startsWith('if')) {
        const varName = stripped.split('=')[0].trim();
        explanations.push(`Line ${lineNum}: Assigns a value to variable '${varName}'`);
      } else if (stripped.startsWith('for ')) {
        explanations.push(`Line ${lineNum}: Starts a for-loop`);
      } else if (stripped.startsWith('if ')) {
        explanations.push(`Line ${lineNum}: Conditional check`);
      } else if (stripped.startsWith('def ') || stripped.startsWith('function ')) {
        const fname = stripped.split('(')[0].replace(/^(def |function )/, '');
        explanations.push(`Line ${lineNum}: Defines function '${fname}'`);
      } else if (stripped.startsWith('return ')) {
        explanations.push(`Line ${lineNum}: Returns a value from the function`);
      } else if (stripped.includes('console.log') || stripped.includes('print(')) {
        explanations.push(`Line ${lineNum}: Prints output to the console`);
      } else {
        explanations.push(`Line ${lineNum}: Executes: ${stripped.slice(0, 60)}`);
      }
    }
    return explanations.join('\n');
  },
});

const checkSyntaxTool = new DynamicStructuredTool({
  name: 'check_syntax',
  description:
    'Check if a JavaScript/TypeScript code snippet has valid syntax. ' +
    "Returns 'Syntax OK' or a description of the syntax error.",
  schema: z.object({
    code: z.string().describe('The code snippet to check'),
  }),
  func: async ({ code }) => {
    try {
      new Function(code);
      return 'Syntax OK -- no syntax errors found.';
    } catch (e: any) {
      return `Syntax error: ${e.message}`;
    }
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const tools = [evaluateExpressionTool, explainCodeTool, checkSyntaxTool];
const graph = createReactAgent({ llm, tools });

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langgraph',
};

const PROMPT = 'Calculate (2**10 - 1) * 3 + 7';

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
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents code_interpreter
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('30-code-interpreter.ts') || process.argv[1]?.endsWith('30-code-interpreter.js')) {
  main().catch(console.error);
}
