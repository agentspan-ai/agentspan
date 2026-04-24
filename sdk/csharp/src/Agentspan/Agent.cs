// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json.Serialization;

namespace Agentspan;

/// <summary>How sub-agents are orchestrated.</summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Strategy
{
    [JsonPropertyName("handoff")]     Handoff,
    [JsonPropertyName("sequential")]  Sequential,
    [JsonPropertyName("parallel")]    Parallel,
    [JsonPropertyName("router")]      Router,
    [JsonPropertyName("round_robin")] RoundRobin,
    [JsonPropertyName("random")]      Random,
    [JsonPropertyName("swarm")]       Swarm,
    [JsonPropertyName("manual")]      Manual,
}

/// <summary>
/// The single orchestration primitive — an LLM + tools, or a multi-agent system.
/// </summary>
public sealed class Agent
{
    public string Name { get; }
    public string? Model { get; set; }
    public string? Instructions { get; set; }
    public PromptTemplate? PromptTemplateInstructions { get; set; }
    public List<ToolDef> Tools { get; set; } = [];
    public List<Agent> Agents { get; set; } = [];
    public Strategy? Strategy { get; set; }
    public Agent? Router { get; set; }
    public int? MaxTurns { get; set; }
    public int? MaxTokens { get; set; }
    public double? Temperature { get; set; }
    public int? TimeoutSeconds { get; set; }
    public bool External { get; set; }
    public bool Planner { get; set; }
    public string? IncludeContents { get; set; }
    public int? ThinkingBudgetTokens { get; set; }
    public List<string>? RequiredTools { get; set; }
    public string? Introduction { get; set; }
    public Dictionary<string, object>? Metadata { get; set; }
    public Type? OutputType { get; set; }
    public List<GuardrailDef> Guardrails { get; set; } = [];
    public TerminationCondition? Termination { get; set; }
    public Dictionary<string, List<string>>? AllowedTransitions { get; set; }

    public Agent(string name)
    {
        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("Agent name cannot be empty.", nameof(name));
        Name = name;
    }

    /// <summary>Sequential pipeline: left >> right >> ...</summary>
    public static Agent operator >>(Agent left, Agent right)
    {
        // If left is already a sequential pipeline (no tools, strategy=Sequential), extend it.
        if (left.Strategy == Agentspan.Strategy.Sequential && left.Tools.Count == 0)
        {
            left.Agents.Add(right);
            return left;
        }

        var pipeline = new Agent($"{left.Name}__{right.Name}")
        {
            Strategy = Agentspan.Strategy.Sequential,
            Agents = [left, right],
        };
        return pipeline;
    }
}

/// <summary>Fluent builder for Agent instances.</summary>
public sealed class AgentBuilder
{
    private readonly Agent _agent;

    private AgentBuilder(Agent agent) => _agent = agent;

    public static AgentBuilder Create(string name) => new(new Agent(name));

    public AgentBuilder WithModel(string model)                     { _agent.Model = model; return this; }
    public AgentBuilder WithInstructions(string instructions)       { _agent.Instructions = instructions; return this; }
    public AgentBuilder WithInstructions(PromptTemplate template)   { _agent.PromptTemplateInstructions = template; return this; }
    public AgentBuilder WithTools(params ToolDef[] tools)           { _agent.Tools.AddRange(tools); return this; }
    public AgentBuilder WithAgents(params Agent[] agents)           { _agent.Agents.AddRange(agents); return this; }
    public AgentBuilder WithStrategy(Strategy strategy)             { _agent.Strategy = strategy; return this; }
    public AgentBuilder WithRouter(Agent router)                    { _agent.Router = router; return this; }
    public AgentBuilder WithOutputType<T>()                         { _agent.OutputType = typeof(T); return this; }
    public AgentBuilder WithMaxTurns(int turns)                     { _agent.MaxTurns = turns; return this; }
    public AgentBuilder WithMaxTokens(int tokens)                   { _agent.MaxTokens = tokens; return this; }
    public AgentBuilder WithTemperature(double temp)                { _agent.Temperature = temp; return this; }
    public AgentBuilder WithTimeout(int seconds)                    { _agent.TimeoutSeconds = seconds; return this; }
    public AgentBuilder WithExternal(bool external = true)          { _agent.External = external; return this; }
    public AgentBuilder WithPlanner(bool planner = true)            { _agent.Planner = planner; return this; }
    public AgentBuilder WithIncludeContents(string mode)            { _agent.IncludeContents = mode; return this; }
    public AgentBuilder WithThinkingBudget(int tokens)              { _agent.ThinkingBudgetTokens = tokens; return this; }
    public AgentBuilder WithRequiredTools(params string[] tools)    { _agent.RequiredTools = [.. tools]; return this; }
    public AgentBuilder WithIntroduction(string intro)              { _agent.Introduction = intro; return this; }
    public AgentBuilder WithMetadata(Dictionary<string, object> m)  { _agent.Metadata = m; return this; }

    public Agent Build()
    {
        if (_agent.Agents.Count > 0 && _agent.Strategy is null)
            throw new ConfigurationException("Strategy required when sub-agents are present.");
        return _agent;
    }
}
