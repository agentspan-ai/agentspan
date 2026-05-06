// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Swarm Orchestration — LLM-driven agent handoffs via transfer tools.
//
// Strategy.Swarm gives the front-line agent transfer_to_<peer> tools.
// The LLM decides which specialist to hand off to by calling the
// appropriate transfer tool.
//
//   support (SWARM)
//   ├── refund_specialist
//   └── tech_support
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Specialist agents ────────────────────────────────────────────────

var refundAgent = new Agent("refund_specialist")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a refund specialist. Process the customer's refund request. " +
        "Check eligibility, confirm the refund amount, and state the timeline. " +
        "Be empathetic and clear. Do NOT ask follow-up questions — " +
        "just process the refund based on what the customer told you.",
};

var techAgent = new Agent("tech_support")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a technical support specialist. Diagnose the customer's " +
        "technical issue and provide clear troubleshooting steps.",
};

// ── Front-line support agent with SWARM handoffs ─────────────────────

var support = new Agent("support")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are the front-line customer support agent. Triage customer requests. " +
        "If the customer needs a refund, transfer to the refund specialist. " +
        "If they have a technical issue, transfer to tech support. " +
        "Use the transfer tools available to you to hand off the conversation.",
    Agents   = [refundAgent, techAgent],
    Strategy = Strategy.Swarm,
    MaxTurns = 3,
};

// ── Run two scenarios ─────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("--- Refund scenario ---");
var result1 = await runtime.RunAsync(
    support,
    "I bought a product last week and it arrived damaged. I want my money back.");
result1.PrintResult();

Console.WriteLine("--- Technical issue scenario ---");
var result2 = await runtime.RunAsync(
    support,
    "My app keeps crashing whenever I try to upload files. It started after the latest update.");
result2.PrintResult();
