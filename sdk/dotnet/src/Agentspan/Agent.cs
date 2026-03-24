using System.Text.RegularExpressions;

namespace Agentspan;

public enum Strategy { Handoff, Sequential, Parallel, Router, RoundRobin, Random, Swarm, Manual }

public sealed class Agent
{
    private static readonly Regex ValidName = new(@"^[a-zA-Z_][a-zA-Z0-9_-]*$");

    public string Name { get; }
    public string Model { get; }
    public string Instructions { get; }
    public IReadOnlyList<ToolDef> Tools { get; }
    public IReadOnlyList<Agent> SubAgents { get; }
    public Strategy Strategy { get; }
    public Agent? Router { get; }
    public IReadOnlyList<Guardrail> Guardrails { get; }
    public int MaxTurns { get; }
    public int? MaxTokens { get; }
    public double? Temperature { get; }
    public int TimeoutSeconds { get; }
    public bool External => string.IsNullOrEmpty(Model);
    public Type? OutputType { get; }

    public Agent(
        string name,
        string model = "",
        string instructions = "",
        IEnumerable<ToolDef>? tools = null,
        IEnumerable<Agent>? subAgents = null,
        Strategy strategy = Strategy.Handoff,
        Agent? router = null,
        IEnumerable<Guardrail>? guardrails = null,
        int maxTurns = 25,
        int? maxTokens = null,
        double? temperature = null,
        int timeoutSeconds = 0,
        Type? outputType = null)
    {
        if (string.IsNullOrEmpty(name)) throw new ArgumentException("Agent name must be non-empty");
        if (!ValidName.IsMatch(name)) throw new ArgumentException($"Invalid agent name '{name}'. Must match ^[a-zA-Z_][a-zA-Z0-9_-]*$");
        if (strategy == Strategy.Router && router == null) throw new ArgumentException("Strategy.Router requires a router");

        Name = name;
        Model = model;
        Instructions = instructions;
        Tools = tools?.ToList().AsReadOnly() ?? Array.Empty<ToolDef>().ToList().AsReadOnly();
        SubAgents = subAgents?.ToList().AsReadOnly() ?? Array.Empty<Agent>().ToList().AsReadOnly();
        Strategy = strategy;
        Router = router;
        Guardrails = guardrails?.ToList().AsReadOnly() ?? Array.Empty<Guardrail>().ToList().AsReadOnly();
        MaxTurns = maxTurns;
        MaxTokens = maxTokens;
        Temperature = temperature;
        TimeoutSeconds = timeoutSeconds;
        OutputType = outputType;
    }

    /// <summary>
    /// >> operator for sequential pipeline. Composes two agents into a Sequential strategy agent.
    /// </summary>
    public static Agent operator >>(Agent left, Agent right)
    {
        var leftAgents = left.Strategy == Strategy.Sequential ? left.SubAgents : new[] { left };
        var rightAgents = right.Strategy == Strategy.Sequential ? right.SubAgents : new[] { right };
        var all = leftAgents.Concat(rightAgents).ToList();
        var name = string.Join("_", all.Select(a => a.Name));
        return new Agent(name, left.Model, subAgents: all, strategy: Strategy.Sequential);
    }

    public override string ToString() =>
        External ? $"Agent(name={Name}, external=True)" : $"Agent(name={Name}, model={Model})";
}
