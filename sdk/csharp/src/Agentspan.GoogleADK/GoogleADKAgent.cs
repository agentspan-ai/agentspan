// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using Agentspan;

namespace Agentspan.GoogleADK;

/// <summary>
/// Bridges the Google ADK (Agent Development Kit) shape to an Agentspan <see cref="Agent"/>.
///
/// <para>Mirrors the Python pattern:</para>
/// <code>
/// from google.adk.agents import Agent
/// agent = Agent(name="greeter", instruction="...", model="gemini-2.0-flash")
/// runtime.run(agent, "Say hi")
/// </code>
///
/// <para>In C# the equivalent is:</para>
/// <code>
/// var agent = GoogleADKAgent.Builder()
///     .Name("greeter")
///     .Instruction("You are a friendly greeter")  // note: singular
///     .Model("gemini-2.0-flash")
///     .Build();
/// await runtime.RunAsync(agent, "Say hi");
/// </code>
///
/// <para>ADK differs from OpenAI in three ways at the wire level:</para>
/// <list type="bullet">
///   <item><description><c>instruction</c> (singular) — not <c>instructions</c></description></item>
///   <item><description><c>sub_agents</c> — not <c>handoffs</c></description></item>
///   <item><description>Bare model names like <c>"gemini-2.0-flash"</c> are prefixed with <c>"google_gemini/"</c> server-side.</description></item>
/// </list>
///
/// <para>The server's <c>GoogleADKNormalizer</c> consumes the wire payload. Tools
/// follow the same <c>[Tool]</c>-attribute reflection as the OpenAI bridge.</para>
/// </summary>
public static class GoogleADKAgent
{
    /// <summary>Start a builder for a Google-ADK-shape Agentspan agent.</summary>
    public static AgentBuilder Builder() => new();

    /// <summary>
    /// Convenience shortcut: build an ADK Agentspan agent from name + model +
    /// instruction + optional tool objects.
    /// </summary>
    public static Agent From(string name, string model, string instruction, params object[] toolObjects)
        => Builder().Name(name).Model(model).Instruction(instruction).Tools(toolObjects).Build();

    public sealed class AgentBuilder
    {
        private string? _name;
        private string? _model;
        private string? _instruction;
        private readonly List<ToolDef> _tools = new();
        private readonly List<Agent> _subAgents = new();
        private string? _outputType;

        public AgentBuilder Name(string name) { _name = name; return this; }
        public AgentBuilder Model(string model) { _model = model; return this; }

        /// <summary>Singular form per ADK convention.</summary>
        public AgentBuilder Instruction(string instruction) { _instruction = instruction; return this; }

        public AgentBuilder Tools(params object[] toolObjects)
        {
            if (toolObjects is null) return this;
            foreach (var obj in toolObjects)
            {
                if (obj is null) continue;
                _tools.AddRange(ToolRegistry.FromInstance(obj));
            }
            return this;
        }

        public AgentBuilder ToolDefs(IEnumerable<ToolDef> defs) { _tools.AddRange(defs); return this; }

        /// <summary>ADK "sub_agents": child agents this agent can delegate to.</summary>
        public AgentBuilder SubAgents(params Agent[] agents) { _subAgents.AddRange(agents); return this; }

        public AgentBuilder OutputType(string typeName) { _outputType = typeName; return this; }

        public Agent Build()
        {
            if (string.IsNullOrEmpty(_name))
                throw new ArgumentException("GoogleADKAgent.Name is required");

            var agent = new Agent(_name)
            {
                Model        = _model,
                // Serializer translates Instructions → "instruction" when framework=google_adk.
                Instructions = _instruction,
                Tools        = _tools,
                Framework    = "google_adk",
            };

            var cfg = new Dictionary<string, object>();
            if (_subAgents.Count > 0)
            {
                var subs = new List<Dictionary<string, object>>();
                foreach (var s in _subAgents)
                {
                    var entry = new Dictionary<string, object> { ["name"] = s.Name };
                    // ADK convention is "instruction" (singular).
                    if (s.Instructions is not null) entry["instruction"] = s.Instructions;
                    if (s.Model        is not null) entry["model"]       = s.Model;
                    subs.Add(entry);
                }
                cfg["sub_agents"] = subs;
            }
            if (!string.IsNullOrEmpty(_outputType)) cfg["output_type"] = _outputType;
            if (cfg.Count > 0) agent.FrameworkConfig = cfg;

            return agent;
        }
    }
}
