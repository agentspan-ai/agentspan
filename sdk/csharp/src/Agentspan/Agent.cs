// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json;
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
    public bool LocalCodeExecution { get; set; }
    public List<string>? AllowedLanguages { get; set; }
    public List<string>? AllowedCommands { get; set; }
    public CodeExecutionConfig? CodeExecution { get; set; }
    public string? IncludeContents { get; set; }
    public int? ThinkingBudgetTokens { get; set; }
    /// <summary>Called before each LLM invocation. Receives the messages list; return empty dict to continue, non-empty to skip LLM.</summary>
    public Func<List<JsonElement>?, Dictionary<string, object>?>? BeforeModelCallback { get; set; }
    /// <summary>Called after each LLM invocation. Receives the LLM result; return empty dict to keep, non-empty to override.</summary>
    public Func<string?, Dictionary<string, object>?>? AfterModelCallback { get; set; }
    public List<string>? RequiredTools { get; set; }
    public string? Introduction { get; set; }
    public Dictionary<string, object>? Metadata { get; set; }
    public Type? OutputType { get; set; }
    public List<GuardrailDef> Guardrails { get; set; } = [];
    public TerminationCondition? Termination { get; set; }
    public Dictionary<string, List<string>>? AllowedTransitions { get; set; }
    /// <summary>
    /// If true, each worker tool for this agent uses domain-based routing so that
    /// all tasks for this execution are sent to the same worker process.
    /// Required for agents that use WaitForMessageTool in stateful (long-running) mode.
    /// </summary>
    public bool Stateful { get; set; }

    public Agent(string name)
    {
        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("Agent name cannot be empty.", nameof(name));
        Name = name;
    }

    /// <summary>
    /// Create a scatter-gather coordinator agent.
    ///
    /// The coordinator decomposes a problem into N independent sub-tasks,
    /// dispatches the worker agent N times in parallel (via agent_tool),
    /// and synthesizes the results. N is determined at runtime by the LLM.
    /// </summary>
    /// <param name="name">Name for the coordinator agent.</param>
    /// <param name="worker">The worker Agent that handles each sub-task.</param>
    /// <param name="model">LLM model for the coordinator. Defaults to worker's model.</param>
    /// <param name="instructions">Additional instructions appended after the auto-generated prefix.</param>
    /// <param name="tools">Extra tools for the coordinator (in addition to the worker tool).</param>
    /// <param name="retryCount">Retries per sub-task on failure.</param>
    /// <param name="retryDelaySeconds">Delay between retries in seconds.</param>
    /// <param name="failFast">When true, a single sub-task failure fails the whole scatter-gather.</param>
    /// <param name="timeoutSeconds">Overall timeout (defaults to 300s for scatter-gather).</param>
    public static Agent ScatterGather(
        string        name,
        Agent         worker,
        string?       model              = null,
        string?       instructions       = null,
        List<ToolDef>? tools             = null,
        int?          retryCount         = null,
        int?          retryDelaySeconds  = null,
        bool          failFast           = false,
        int?          timeoutSeconds     = null)
    {
        const string prefix =
            "You are a coordinator that decomposes problems into independent sub-tasks.\n\n" +
            "WORKFLOW:\n" +
            "1. Analyze the input and identify independent sub-problems\n" +
            "2. Call the '{worker}' tool MULTIPLE TIMES IN PARALLEL — once per sub-problem, each with a clear, self-contained prompt\n" +
            "3. After all results return, synthesize them into a unified answer\n\n" +
            "IMPORTANT: Issue all '{worker}' tool calls in a SINGLE response to maximize parallelism.\n";

        var workerTool = AgentTool.Create(
            agent:              worker,
            retryCount:         retryCount,
            retryDelaySeconds:  retryDelaySeconds,
            optional:           !failFast ? true : null);

        var allTools = new List<ToolDef> { workerTool };
        if (tools is not null) allTools.AddRange(tools);

        var fullInstructions = instructions is not null
            ? prefix.Replace("{worker}", worker.Name) + "\n" + instructions
            : prefix.Replace("{worker}", worker.Name);

        return new Agent(name)
        {
            Model          = model ?? worker.Model,
            Instructions   = fullInstructions,
            Tools          = allTools,
            TimeoutSeconds = timeoutSeconds ?? 300,
        };
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
