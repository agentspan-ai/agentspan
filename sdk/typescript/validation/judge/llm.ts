/**
 * LLM judge scoring — individual and comparison.
 *
 * Uses fetch to call OpenAI-compatible chat completions endpoint.
 * Prefers OPENAI_API_KEY directly, falls back to agentspan server LLM proxy.
 */

import { JUDGE_SYSTEM_PROMPT, buildIndividualPrompt, buildComparisonPrompt } from './rubrics.js';

export interface JudgeConfig {
  model: string;
  maxTokens: number;
  maxOutputChars: number;
}

interface JudgeResponse {
  score: number;
  reason: string;
}

/**
 * Truncate output to maxOutputChars, appending [truncated] marker.
 */
function truncateOutput(output: string, maxChars: number): string {
  if (output.length > maxChars) {
    return output.slice(0, maxChars) + '\n[truncated]';
  }
  return output;
}

/**
 * Validate and clamp a judge response score to 1-5.
 */
function validateResponse(parsed: Record<string, unknown>): JudgeResponse {
  let score = parsed.score as number | undefined;
  const reason = (parsed.reason ?? parsed.error ?? '') as string;

  if (score == null || typeof score !== 'number') {
    return { score: 0, reason: String(reason) };
  }

  if (score < 1 || score > 5) {
    score = Math.max(1, Math.min(5, Math.round(score)));
  }

  return { score, reason: String(reason) };
}

/**
 * Call the LLM judge with a system prompt and user prompt.
 */
async function callJudge(
  systemPrompt: string,
  userPrompt: string,
  config: JudgeConfig,
): Promise<JudgeResponse> {
  const apiKey = process.env.OPENAI_API_KEY;
  const endpoint = apiKey
    ? 'https://api.openai.com/v1/chat/completions'
    : `${process.env.AGENTSPAN_SERVER_URL ?? 'http://localhost:8080/api'}/llm/chat/completions`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`;
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model: config.model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: 0,
      max_tokens: config.maxTokens,
      response_format: { type: 'json_object' },
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Judge API returned ${response.status}: ${body}`);
  }

  const data = (await response.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };

  const content = data.choices?.[0]?.message?.content?.trim() ?? '';

  try {
    const parsed = JSON.parse(content) as Record<string, unknown>;
    return validateResponse(parsed);
  } catch {
    // Try to extract JSON from content
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0]) as Record<string, unknown>;
        return validateResponse(parsed);
      } catch {
        // fall through
      }
    }
    return { score: 0, reason: `Failed to parse judge response: ${content.slice(0, 200)}` };
  }
}

/**
 * Judge a single example's output on a 1-5 scale.
 *
 * @param prompt - The task prompt that was given to the agent
 * @param output - The agent's output text
 * @param config - Judge configuration (model, max tokens, max output chars)
 * @returns Score (1-5) and reasoning
 */
export async function judgeOutput(
  prompt: string,
  output: string,
  config: JudgeConfig,
): Promise<JudgeResponse> {
  if (!output.trim()) {
    return { score: 0, reason: 'empty output' };
  }

  const truncated = truncateOutput(output, config.maxOutputChars);
  const userPrompt = buildIndividualPrompt(prompt, truncated);
  return callJudge(JUDGE_SYSTEM_PROMPT, userPrompt, config);
}

/**
 * Compare agentspan output against native framework output on a 1-5 scale.
 *
 * @param prompt - The task prompt
 * @param nativeOutput - Output from native framework execution (baseline)
 * @param agentspanOutput - Output from agentspan execution (candidate)
 * @param config - Judge configuration
 * @returns Score (1-5) and reasoning
 */
export async function judgeComparison(
  prompt: string,
  nativeOutput: string,
  agentspanOutput: string,
  config: JudgeConfig,
): Promise<JudgeResponse> {
  const truncatedNative = truncateOutput(nativeOutput, config.maxOutputChars);
  const truncatedAgentspan = truncateOutput(agentspanOutput, config.maxOutputChars);
  const userPrompt = buildComparisonPrompt(prompt, truncatedNative, truncatedAgentspan);
  return callJudge(JUDGE_SYSTEM_PROMPT, userPrompt, config);
}
