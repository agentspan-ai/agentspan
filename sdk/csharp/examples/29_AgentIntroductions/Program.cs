// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Agent Introductions — agents introduce themselves before a group discussion.
//
// The Introduction property adds a self-introduction to the conversation
// transcript at the start of multi-agent group chats, helping agents
// understand who they're collaborating with.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Agents with introductions ─────────────────────────────────────────

var architect = new Agent("architect")
{
    Model        = Settings.LlmModel,
    Introduction =
        "I am the Software Architect. I focus on system design, scalability, " +
        "and technical trade-offs. I'll evaluate proposals from an architecture perspective.",
    Instructions =
        "You are a software architect. Focus on system design, scalability, " +
        "and architectural patterns. Keep responses to 2-3 paragraphs.",
};

var securityEngineer = new Agent("security_engineer")
{
    Model        = Settings.LlmModel,
    Introduction =
        "I am the Security Engineer. I focus on threat modeling, authentication, " +
        "authorization, and data protection. I'll flag any security concerns.",
    Instructions =
        "You are a security engineer. Focus on security implications, " +
        "vulnerabilities, and best practices. Keep responses to 2-3 paragraphs.",
};

var productManager = new Agent("product_manager")
{
    Model        = Settings.LlmModel,
    Introduction =
        "I am the Product Manager. I focus on user needs, business value, " +
        "and delivery timelines. I'll ensure we stay focused on what matters to customers.",
    Instructions =
        "You are a product manager. Focus on user needs, business value, " +
        "and prioritization. Keep responses to 2-3 paragraphs.",
};

// ── Team discussion with introductions ───────────────────────────────

// Introductions are automatically prepended to the conversation transcript
// before the first turn, so each agent knows who's in the room.
var designReview = new Agent("design_review")
{
    Model    = Settings.LlmModel,
    Agents   = [architect, securityEngineer, productManager],
    Strategy = Strategy.RoundRobin,
    MaxTurns = 6,
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    designReview,
    "We need to design a new user authentication system for our SaaS platform. " +
    "Should we use OAuth 2.0, SAML, or build our own JWT-based system?");

result.PrintResult();
