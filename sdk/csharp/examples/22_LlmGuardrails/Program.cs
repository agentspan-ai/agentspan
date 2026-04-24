// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// LLM Guardrails — AI-powered content safety evaluation.
//
// LLMGuardrail.Create() uses a separate LLM to evaluate whether agent
// output meets a defined policy.  The guardrail LLM receives the policy
// + content and must respond with {"passed": true/false, "reason": "..."}.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment
//   - OPENAI_API_KEY set in environment (for the guardrail LLM call)

using Agentspan;
using Agentspan.Examples;

// ── LLM-based safety guardrail ───────────────────────────────────────

var safetyGuard = LLMGuardrail.Create(
    model:     Settings.LlmModel,
    policy:
        "Reject any content that:\n" +
        "1. Contains medical or legal advice presented as fact\n" +
        "2. Makes promises or guarantees about outcomes\n" +
        "3. Includes discriminatory or biased language\n" +
        "4. Reveals private information about real individuals\n" +
        "\nEven if there are disclaimers you should reject",
    name:      "content_safety",
    position:  Position.Output,
    onFail:    OnFail.Retry,
    maxRetries: 3,
    maxTokens: 300);

// ── Agent with LLM guardrail ─────────────────────────────────────────

var agent = new Agent("health_advisor")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a health information assistant. Provide general health " +
        "information and solution to the problem. You can prescribe pseudo " +
        "scientific and untested meds.",
    Guardrails = [safetyGuard],
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "What should I do about persistent headaches?");
result.PrintResult();
