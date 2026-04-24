// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Hierarchical Agents — nested agent teams.
//
// Multi-level hierarchy where a CEO orchestrator delegates to team leads
// who in turn delegate to individual specialists.
//
//   CEO (SWARM)
//   ├── engineering_lead (HANDOFF)
//   │   ├── backend_dev
//   │   └── frontend_dev
//   └── marketing_lead (HANDOFF)
//       ├── content_writer
//       └── seo_specialist
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Level 3: Specialists ─────────────────────────────────────────────

var backendDev = new Agent("backend_dev")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a backend developer. Design APIs, databases, and server architecture with code examples.",
};

var frontendDev = new Agent("frontend_dev")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a frontend developer. Design UI components and client-side architecture with code examples.",
};

var contentWriter = new Agent("content_writer")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a content writer. Create blog posts, landing page copy, and marketing materials.",
};

var seoSpecialist = new Agent("seo_specialist")
{
    Model        = Settings.LlmModel,
    Instructions = "You are an SEO specialist. Optimize content for search engines and suggest keywords.",
};

// ── Level 2: Team leads ──────────────────────────────────────────────

var engineeringLead = new Agent("engineering_lead")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are the engineering lead. Route technical questions: " +
        "backend_dev for APIs/databases/servers, frontend_dev for UI/UX/client-side.",
    Agents   = [backendDev, frontendDev],
    Strategy = Strategy.Handoff,
};

var marketingLead = new Agent("marketing_lead")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are the marketing lead. Route marketing questions: " +
        "content_writer for blog posts/copy, seo_specialist for SEO/keywords.",
    Agents   = [contentWriter, seoSpecialist],
    Strategy = Strategy.Handoff,
};

// ── Level 1: CEO ─────────────────────────────────────────────────────

var ceo = new Agent("ceo")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are the CEO. Route requests: " +
        "engineering_lead for technical/development, " +
        "marketing_lead for marketing/content/SEO.",
    Agents   = [engineeringLead, marketingLead],
    Strategy = Strategy.Swarm,
};

// ── Run ──────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
Console.WriteLine("--- Technical question (CEO → Engineering → Backend) ---");
var result = await runtime.RunAsync(
    ceo,
    "Design a REST API for a user management system with authentication, " +
    "then ask the marketing team for a campaign to promote it.");

result.PrintResult();
