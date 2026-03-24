/**
 * Code Interpreter -- agent that writes and safely evaluates expressions.
 *
 * Demonstrates:
 *   - An agent that generates and explains code
 *   - Safe expression evaluation for numeric calculations
 *   - Code explanation and syntax checking
 *   - Practical use case: interactive coding assistant
 *
 * In production you would use:
 *   import { tool } from '@langchain/core/tools';
 *   import { createReactAgent } from '@langchain/langgraph/prebuilt';
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool implementations
// ---------------------------------------------------------------------------

function evaluateExpression(expression: string): string {
  try {
    // Safe evaluation: only allow basic arithmetic
    const sanitized = expression.replace(/[^0-9+\-*/().%\s]/g, '');
    if (sanitized !== expression.replace(/\s+/g, '').replace(/\*\*/g, '**')) {
      // Allow ** for exponentiation
    }
    // Use Function constructor for safe-ish math eval
    const result = Function('"use strict"; return (' + expression.replace(/\*\*/g, '**') + ')')();
    return `${expression} = ${result}`;
  } catch (e) {
    return `Error evaluating '${expression}': ${e}`;
  }
}

function explainCode(code: string): string {
  const lines = code.trim().split('\n');
  const explanations: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const stripped = lines[i].trim();
    if (!stripped || stripped.startsWith('#') || stripped.startsWith('//')) {
      explanations.push(`Line ${i + 1}: (comment or blank)`);
    } else if (stripped.includes('=') && !stripped.startsWith('if')) {
      const varName = stripped.split('=')[0].trim();
      explanations.push(`Line ${i + 1}: Assigns a value to variable '${varName}'`);
    } else if (stripped.startsWith('for ')) {
      explanations.push(`Line ${i + 1}: Starts a for-loop`);
    } else if (stripped.startsWith('if ')) {
      explanations.push(`Line ${i + 1}: Conditional check`);
    } else if (stripped.startsWith('function ') || stripped.startsWith('def ')) {
      const fname = stripped.split('(')[0].replace(/^(function|def)\s+/, '');
      explanations.push(`Line ${i + 1}: Defines function '${fname}'`);
    } else if (stripped.startsWith('return ')) {
      explanations.push(`Line ${i + 1}: Returns a value from the function`);
    } else if (stripped.startsWith('print(') || stripped.startsWith('console.log(')) {
      explanations.push(`Line ${i + 1}: Prints output to the console`);
    } else {
      explanations.push(`Line ${i + 1}: Executes: ${stripped.slice(0, 60)}`);
    }
  }
  return explanations.join('\n');
}

function checkSyntax(code: string): string {
  try {
    // Use Function constructor to check JS syntax
    new Function(code);
    return 'Syntax OK -- no syntax errors found.';
  } catch (e) {
    return `Syntax error: ${(e as Error).message}`;
  }
}

// ---------------------------------------------------------------------------
// Tool dispatcher
// ---------------------------------------------------------------------------
function dispatch(query: string): string {
  const q = query.toLowerCase();
  if (q.includes('calculate') || q.includes('evaluate') || /^\(?\d/.test(query.trim())) {
    const expr = query.replace(/^(calculate|evaluate)\s+/i, '').trim();
    return evaluateExpression(expr);
  }
  if (q.includes('check') && q.includes('syntax')) {
    const code = query.replace(/^check\s+the\s+syntax\s+of:\s*/i, '').trim();
    return checkSyntax(code);
  }
  if (q.includes('explain')) {
    const code = query.replace(/^explain\s+this\s+code:\s*/i, '').trim();
    return explainCode(code);
  }
  return evaluateExpression(query);
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'code_interpreter_agent',

  invoke: async (input: Record<string, unknown>) => {
    const query = (input.input as string) ?? '';
    const result = dispatch(query);
    return {
      messages: [
        { role: 'user', content: query },
        { role: 'assistant', content: result },
      ],
    };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['agent', {}],
      ['tools', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'agent'],
      ['agent', 'tools'],
      ['tools', 'agent'],
      ['agent', '__end__'],
    ],
  }),

  nodes: new Map([
    ['agent', {}],
    ['tools', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const query = (input.input as string) ?? '';
    const result = dispatch(query);
    yield ['updates', { agent: { messages: [{ role: 'assistant', content: result }] } }];
    yield ['values', { messages: [{ role: 'assistant', content: result }] }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const queries = [
    'Calculate (2**10 - 1) * 3 + 7',
    "Check the syntax of: function hello( { console.log('hi') }",
    'Explain this code:\nfor (let i = 0; i < 5; i++) {\n  console.log(i * 2);\n}',
  ];

  const runtime = new AgentRuntime();
  try {
    for (const query of queries) {
      console.log(`\nQuery: ${query}`);
      const result = await runtime.run(graph, query);
      result.printResult();
      console.log('-'.repeat(60));
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
