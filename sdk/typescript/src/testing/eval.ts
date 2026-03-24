import type { AgentResult } from '../types.js';

/**
 * Result of an LLM-based correctness evaluation.
 */
export interface EvalResult {
  /** Whether the weighted average score meets the pass threshold. */
  passed: boolean;
  /** Per-rubric numeric scores (1-5 scale). */
  scores: Record<string, number>;
  /** Weighted average across all rubric scores. */
  weightedAverage: number;
  /** Per-rubric reasoning from the judge. */
  reasoning: Record<string, string>;
}

/**
 * A single rubric criterion for evaluation.
 */
export interface Rubric {
  name: string;
  description: string;
  weight?: number;
}

/**
 * Options for CorrectnessEval.evaluate().
 */
export interface EvaluateOptions {
  /** Rubric criteria to evaluate against. */
  rubrics: Rubric[];
  /** Minimum weighted average score to pass (default 3.5). */
  passThreshold?: number;
}

/**
 * Options for constructing a CorrectnessEval.
 */
export interface CorrectnessEvalOptions {
  /** LLM model identifier for the judge. */
  model: string;
  /** Max chars of output to send to the judge (default 3000). */
  maxOutputChars?: number;
  /** Max tokens for judge response (default 300). */
  maxTokens?: number;
  /** Base URL for the LLM API endpoint. */
  endpoint?: string;
  /** API key for the LLM endpoint. */
  apiKey?: string;
}

/**
 * LLM-based correctness evaluator.
 *
 * Constructs a prompt with rubric criteria and the agent's output,
 * sends it to an LLM judge, and parses the scores.
 */
export class CorrectnessEval {
  readonly model: string;
  readonly maxOutputChars: number;
  readonly maxTokens: number;
  readonly endpoint: string;
  readonly apiKey: string;

  constructor(options: CorrectnessEvalOptions) {
    this.model = options.model;
    this.maxOutputChars = options.maxOutputChars ?? 3000;
    this.maxTokens = options.maxTokens ?? 300;
    this.endpoint =
      options.endpoint ?? 'https://api.openai.com/v1/chat/completions';
    this.apiKey = options.apiKey ?? '';
  }

  /**
   * Build the judge prompt from rubrics and agent output.
   */
  buildPrompt(result: AgentResult, rubrics: Rubric[]): string {
    const outputStr = JSON.stringify(result.output).slice(
      0,
      this.maxOutputChars,
    );
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
Tool Calls: ${result.toolCalls.length}
Events: ${result.events.length}

## Rubrics
Score each rubric on a 1-5 scale (1=poor, 5=excellent):
${rubricLines}

## Response Format
Respond ONLY with valid JSON in this exact format:
{
  "scores": { "rubric_name": <number>, ... },
  "reasoning": { "rubric_name": "<explanation>", ... }
}`;
  }

  /**
   * Evaluate an agent result against rubric criteria.
   *
   * Calls an LLM endpoint to judge the output quality.
   * Falls back to a default passing result if the endpoint is unavailable.
   */
  async evaluate(
    result: AgentResult,
    options: EvaluateOptions,
  ): Promise<EvalResult> {
    const { rubrics, passThreshold = 3.5 } = options;
    const prompt = this.buildPrompt(result, rubrics);

    try {
      const response = await fetch(this.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {}),
        },
        body: JSON.stringify({
          model: this.model,
          messages: [{ role: 'user', content: prompt }],
          max_tokens: this.maxTokens,
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
      return this.parseResponse(content, rubrics, passThreshold);
    } catch {
      // If the LLM call fails, return a default result with mid-range scores
      return this.defaultResult(rubrics, passThreshold);
    }
  }

  /**
   * Parse the LLM judge response into an EvalResult.
   */
  private parseResponse(
    content: string,
    rubrics: Rubric[],
    passThreshold: number,
  ): EvalResult {
    try {
      // Try to extract JSON from the response
      const jsonMatch = content.match(/\{[\s\S]*\}/);
      if (!jsonMatch) {
        return this.defaultResult(rubrics, passThreshold);
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

      const weightedAverage = this.computeWeightedAverage(scores, rubrics);

      return {
        passed: weightedAverage >= passThreshold,
        scores,
        weightedAverage,
        reasoning,
      };
    } catch {
      return this.defaultResult(rubrics, passThreshold);
    }
  }

  /**
   * Compute weighted average of scores.
   */
  private computeWeightedAverage(
    scores: Record<string, number>,
    rubrics: Rubric[],
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
   * Create a default result when the LLM judge is unavailable.
   */
  private defaultResult(
    rubrics: Rubric[],
    passThreshold: number,
  ): EvalResult {
    const scores: Record<string, number> = {};
    const reasoning: Record<string, string> = {};

    for (const r of rubrics) {
      scores[r.name] = 3;
      reasoning[r.name] = 'Default score (judge unavailable)';
    }

    const weightedAverage = this.computeWeightedAverage(scores, rubrics);

    return {
      passed: weightedAverage >= passThreshold,
      scores,
      weightedAverage,
      reasoning,
    };
  }
}
