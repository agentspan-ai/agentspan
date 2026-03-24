import type { AgentResult } from '../types.js';
import type { JudgeConfig } from './config.js';

/**
 * Rubric criterion for LLM judge evaluation.
 */
export interface JudgeRubric {
  name: string;
  description: string;
  weight?: number;
}

/**
 * Result from the LLM judge.
 */
export interface JudgeResult {
  passed: boolean;
  scores: Record<string, number>;
  weightedAverage: number;
  reasoning: Record<string, string>;
}

/**
 * Build the judge prompt.
 */
function buildJudgePrompt(
  result: AgentResult,
  rubrics: JudgeRubric[],
  maxOutputChars: number,
): string {
  const outputStr = JSON.stringify(result.output).slice(0, maxOutputChars);
  const rubricLines = rubrics
    .map(
      (r, i) =>
        `${i + 1}. ${r.name} (weight: ${r.weight ?? 1}): ${r.description}`,
    )
    .join('\n');

  return `You are an AI judge evaluating an agent's output quality.

## Agent Output
${outputStr}

## Agent Status
Status: ${result.status}
Finish Reason: ${result.finishReason}

## Rubrics
Score each rubric on a 1-5 scale (1=poor, 5=excellent):
${rubricLines}

## Response Format
Respond ONLY with valid JSON:
{
  "scores": { "rubric_name": <number>, ... },
  "reasoning": { "rubric_name": "<explanation>", ... }
}`;
}

/**
 * Compute weighted average of scores.
 */
function computeWeightedAverage(
  scores: Record<string, number>,
  rubrics: JudgeRubric[],
): number {
  let totalWeight = 0;
  let weightedSum = 0;

  for (const r of rubrics) {
    const weight = r.weight ?? 1;
    const score = scores[r.name] ?? 0;
    totalWeight += weight;
    weightedSum += score * weight;
  }

  return totalWeight > 0 ? weightedSum / totalWeight : 0;
}

/**
 * Judge an agent result against rubric criteria using an LLM.
 */
export async function judgeResult(
  result: AgentResult,
  rubrics: JudgeRubric[],
  config: JudgeConfig,
  options?: { endpoint?: string; apiKey?: string; passThreshold?: number },
): Promise<JudgeResult> {
  const maxOutputChars = config.maxOutputChars ?? 3000;
  const passThreshold = options?.passThreshold ?? 3.5;
  const endpoint =
    options?.endpoint ?? 'https://api.openai.com/v1/chat/completions';
  const apiKey = options?.apiKey ?? '';
  const prompt = buildJudgePrompt(result, rubrics, maxOutputChars);

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      },
      body: JSON.stringify({
        model: config.model,
        messages: [{ role: 'user', content: prompt }],
        max_tokens: config.maxTokens ?? 300,
        temperature: 0,
      }),
    });

    if (!response.ok) {
      throw new Error(`Judge API returned ${response.status}`);
    }

    const data = (await response.json()) as {
      choices?: Array<{ message?: { content?: string } }>;
    };
    const content = data.choices?.[0]?.message?.content ?? '';

    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return defaultJudgeResult(rubrics, passThreshold);
    }

    const parsed = JSON.parse(jsonMatch[0]) as {
      scores?: Record<string, number>;
      reasoning?: Record<string, string>;
    };

    const scores: Record<string, number> = {};
    const reasoning: Record<string, string> = {};

    for (const r of rubrics) {
      scores[r.name] = parsed.scores?.[r.name] ?? 3;
      reasoning[r.name] = parsed.reasoning?.[r.name] ?? '';
    }

    const weightedAverage = computeWeightedAverage(scores, rubrics);

    return {
      passed: weightedAverage >= passThreshold,
      scores,
      weightedAverage,
      reasoning,
    };
  } catch {
    return defaultJudgeResult(rubrics, passThreshold);
  }
}

/**
 * Default judge result when LLM is unavailable.
 */
function defaultJudgeResult(
  rubrics: JudgeRubric[],
  passThreshold: number,
): JudgeResult {
  const scores: Record<string, number> = {};
  const reasoning: Record<string, string> = {};

  for (const r of rubrics) {
    scores[r.name] = 3;
    reasoning[r.name] = 'Default score (judge unavailable)';
  }

  const weightedAverage = computeWeightedAverage(scores, rubrics);

  return {
    passed: weightedAverage >= passThreshold,
    scores,
    weightedAverage,
    reasoning,
  };
}
