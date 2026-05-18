// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// OpenAi03 — Structured Output.
//
// Forces an OpenAI Agents SDK agent to return a typed JSON object via
// the .OutputType("MovieList") hook. Server-side, the normalizer pins
// the LLM to that schema.
//
// Note: simplified from Java original — temperature/max_tokens not
// surfaced on the OpenAIAgent builder yet (Python parity gap, same as Java).
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.OpenAI;

var agent = OpenAIAgent.Builder()
    .Name("movie_recommender")
    .Instructions(
        "You are a movie recommendation expert. When asked for movie suggestions, " +
        "return a structured list of recommendations with title, year, genre, " +
        "and a brief reason for each recommendation. Identify the overall theme.")
    .Model(Settings.LlmModel)
    .OutputType("MovieList")
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(
    agent,
    "Recommend 3 sci-fi movies that explore the concept of artificial intelligence.");
result.PrintResult();
