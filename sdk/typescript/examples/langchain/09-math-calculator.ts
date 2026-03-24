/**
 * Math Calculator -- agent with comprehensive mathematical tools.
 *
 * Demonstrates:
 *   - A suite of math tools: arithmetic, quadratic, circle, prime factorization, statistics
 *   - ChatOpenAI selecting the right tool for each problem
 *   - Multiple sequential queries using the same agent pattern
 *   - Running via AgentRuntime
 *
 * Requires: OPENAI_API_KEY environment variable
 */

import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { HumanMessage, AIMessage, ToolMessage, SystemMessage } from '@langchain/core/messages';
import { RunnableLambda } from '@langchain/core/runnables';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Math tool definitions ────────────────────────────────

const arithmeticTool = new DynamicStructuredTool({
  name: 'basic_arithmetic',
  description: 'Evaluate a basic arithmetic expression. Supports +, -, *, /, (), and %.',
  schema: z.object({
    expression: z.string().describe('The arithmetic expression to evaluate, e.g. "(15 * 4 + 8) / 7"'),
  }),
  func: async ({ expression }) => {
    try {
      const sanitized = expression.replace(/[^0-9+\-*/().%\s]/g, '');
      const result = Function(`"use strict"; return (${sanitized})`)();
      return `${expression} = ${result}`;
    } catch {
      return `Error: could not evaluate '${expression}'`;
    }
  },
});

const quadraticTool = new DynamicStructuredTool({
  name: 'solve_quadratic',
  description: 'Solve a quadratic equation ax^2 + bx + c = 0. Returns real or complex roots.',
  schema: z.object({
    a: z.number().describe('Coefficient of x^2'),
    b: z.number().describe('Coefficient of x'),
    c: z.number().describe('Constant term'),
  }),
  func: async ({ a, b, c }) => {
    const discriminant = b ** 2 - 4 * a * c;
    if (discriminant > 0) {
      const x1 = (-b + Math.sqrt(discriminant)) / (2 * a);
      const x2 = (-b - Math.sqrt(discriminant)) / (2 * a);
      return `Two real roots: x1 = ${x1.toFixed(6)}, x2 = ${x2.toFixed(6)}`;
    } else if (discriminant === 0) {
      const x = -b / (2 * a);
      return `One real root: x = ${x.toFixed(6)}`;
    } else {
      const real = -b / (2 * a);
      const imag = Math.sqrt(-discriminant) / (2 * a);
      return `Complex roots: x1 = ${real.toFixed(4)}+${imag.toFixed(4)}i, x2 = ${real.toFixed(4)}-${imag.toFixed(4)}i`;
    }
  },
});

const circleTool = new DynamicStructuredTool({
  name: 'circle_properties',
  description: 'Calculate properties of a circle given its radius: diameter, circumference, and area.',
  schema: z.object({
    radius: z.number().describe('Radius of the circle'),
  }),
  func: async ({ radius }) => {
    const area = Math.PI * radius ** 2;
    const circumference = 2 * Math.PI * radius;
    const diameter = 2 * radius;
    return [
      `Circle (r=${radius}):`,
      `  Diameter:      ${diameter.toFixed(4)}`,
      `  Circumference: ${circumference.toFixed(4)}`,
      `  Area:          ${area.toFixed(4)}`,
    ].join('\n');
  },
});

const primeFactorsTool = new DynamicStructuredTool({
  name: 'prime_factorization',
  description: 'Find the prime factorization of a positive integer.',
  schema: z.object({
    n: z.number().describe('The positive integer to factorize'),
  }),
  func: async ({ n }) => {
    if (n < 2) return `${n} has no prime factors.`;
    const factors: number[] = [];
    let temp = n;
    let d = 2;
    while (d * d <= temp) {
      while (temp % d === 0) {
        factors.push(d);
        temp = Math.floor(temp / d);
      }
      d++;
    }
    if (temp > 1) factors.push(temp);
    return `${n} = ${factors.join(' x ')}`;
  },
});

const statisticsTool = new DynamicStructuredTool({
  name: 'statistics_summary',
  description: 'Compute statistics (count, mean, median, stddev, min, max) for a list of numbers.',
  schema: z.object({
    numbers: z.string().describe('Comma-separated list of numbers, e.g. "12, 45, 23, 67"'),
  }),
  func: async ({ numbers }) => {
    const nums = numbers.split(',').map((x) => parseFloat(x.trim())).filter((n) => !isNaN(n));
    if (nums.length < 2) return 'Provide at least 2 numbers.';

    const mean = nums.reduce((a, b) => a + b, 0) / nums.length;
    const sorted = [...nums].sort((a, b) => a - b);
    const median = sorted.length % 2 === 0
      ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
      : sorted[Math.floor(sorted.length / 2)];
    const variance = nums.reduce((sum, n) => sum + (n - mean) ** 2, 0) / (nums.length - 1);
    const stddev = Math.sqrt(variance);

    return [
      `Count:  ${nums.length}`,
      `Mean:   ${mean.toFixed(4)}`,
      `Median: ${median.toFixed(4)}`,
      `StdDev: ${stddev.toFixed(4)}`,
      `Min:    ${Math.min(...nums)}`,
      `Max:    ${Math.max(...nums)}`,
    ].join('\n');
  },
});

// ── Agent loop ───────────────────────────────────────────

const tools = [arithmeticTool, quadraticTool, circleTool, primeFactorsTool, statisticsTool];
const toolMap = Object.fromEntries(tools.map((t) => [t.name, t]));

async function runMathAgent(prompt: string): Promise<string> {
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);

  const messages: (SystemMessage | HumanMessage | AIMessage | ToolMessage)[] = [
    new SystemMessage(
      'You are a math tutor and calculator. Use the provided tools to solve problems accurately. ' +
      'Show the tool results clearly in your response.'
    ),
    new HumanMessage(prompt),
  ];

  for (let i = 0; i < 5; i++) {
    const response = await model.invoke(messages);
    messages.push(response);

    const toolCalls = response.tool_calls ?? [];
    if (toolCalls.length === 0) {
      return typeof response.content === 'string'
        ? response.content
        : JSON.stringify(response.content);
    }

    for (const tc of toolCalls) {
      const tool = toolMap[tc.name];
      if (tool) {
        const result = await (tool as any).invoke(tc.args);
        messages.push(new ToolMessage({ content: String(result), tool_call_id: tc.id! }));
      }
    }
  }

  return 'Agent reached maximum iterations.';
}

// ── Wrap for Agentspan ───────────────────────────────────

const agentRunnable = new RunnableLambda({
  func: async (input: { input: string }) => {
    const output = await runMathAgent(input.input);
    return { output };
  },
});

// Add agentspan metadata for extraction
(agentRunnable as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langchain',
};

async function main() {
  const runtime = new AgentRuntime();

  const problems = [
    'What is (15 * 4 + 8) / 7?',
    'Solve 2x^2 - 5x + 3 = 0',
    'What are the properties of a circle with radius 7?',
    'Find the prime factorization of 360.',
    'Give me statistics for: 12, 45, 23, 67, 34, 89, 11, 55',
  ];

  try {
    for (const problem of problems) {
      console.log(`\n${'='.repeat(60)}`);
      console.log(`Problem: ${problem}`);
      const result = await runtime.run(agentRunnable, problem);
      console.log('Status:', result.status);
      result.printResult();
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
