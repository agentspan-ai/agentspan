// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using Agentspan;

namespace Agentspan.OpenAI;

/// <summary>
/// Bridges the OpenAI Agents SDK shape to an Agentspan <see cref="Agent"/>.
///
/// <para>Mirrors the Python pattern:</para>
/// <code>
/// from agents import Agent
/// agent = Agent(name="greeter", instructions="...", model="openai/gpt-4o-mini")
/// runtime.run(agent, "Say hi")
/// </code>
///
/// <para>In C# the equivalent is:</para>
/// <code>
/// var agent = OpenAIAgent.Builder()
///     .Name("greeter")
///     .Instructions("You are a helpful assistant")
///     .Model("openai/gpt-4o-mini")
///     .Build();
/// await runtime.RunAsync(agent, "Say hi");
/// </code>
///
/// <para>The server's <c>OpenAINormalizer</c> consumes the wire payload (the SDK
/// routes through <c>framework="openai"</c> + a raw config map). Model names
/// without a provider prefix are auto-prefixed with <c>openai/</c> server-side.</para>
///
/// <para>Tool objects passed to the Tools method are scanned for
/// <c>[Tool]</c>-annotated methods via <c>ToolRegistry.FromInstance</c>.
/// Each method becomes an Agentspan worker tool; the OpenAI Agents server-side
/// runner calls them via the standard tool-call dispatch.</para>
/// </summary>
public static class OpenAIAgent
{
    /// <summary>Start a builder for an OpenAI-shape Agentspan agent.</summary>
    public static AgentBuilder Builder() => new();

    /// <summary>
    /// Convenience shortcut: build an OpenAI Agentspan agent from name + model +
    /// instructions + optional tool objects.
    /// </summary>
    public static Agent From(string name, string model, string instructions, params object[] toolObjects)
        => Builder().Name(name).Model(model).Instructions(instructions).Tools(toolObjects).Build();

    public sealed class AgentBuilder
    {
        private string? _name;
        private string? _model;
        private string? _instructions;
        private readonly List<ToolDef> _tools = new();
        private readonly List<Agent> _handoffs = new();
        private string? _outputType;

        public AgentBuilder Name(string name) { _name = name; return this; }
        public AgentBuilder Model(string model) { _model = model; return this; }
        public AgentBuilder Instructions(string instructions) { _instructions = instructions; return this; }

        /// <summary>Add objects whose public methods carry <c>[Tool]</c>. Each becomes a worker tool.</summary>
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

        /// <summary>Add already-built <see cref="ToolDef"/>s (e.g. http_tool, mcp_tool).</summary>
        public AgentBuilder ToolDefs(IEnumerable<ToolDef> defs) { _tools.AddRange(defs); return this; }

        /// <summary>OpenAI Agents SDK "handoffs": sub-agents the LLM can transfer control to.</summary>
        public AgentBuilder Handoffs(params Agent[] agents) { _handoffs.AddRange(agents); return this; }

        /// <summary>Optional structured-output type name passed via raw config.</summary>
        public AgentBuilder OutputType(string typeName) { _outputType = typeName; return this; }

        public Agent Build()
        {
            if (string.IsNullOrEmpty(_name))
                throw new ArgumentException("OpenAIAgent.Name is required");

            var agent = new Agent(_name)
            {
                Model        = _model,
                Instructions = _instructions,
                Tools        = _tools,
                Framework    = "openai",
            };

            var cfg = new Dictionary<string, object>();
            if (_handoffs.Count > 0)
            {
                var hs = new List<Dictionary<string, object>>();
                foreach (var h in _handoffs)
                {
                    var entry = new Dictionary<string, object> { ["name"] = h.Name };
                    if (h.Instructions is not null) entry["instructions"] = h.Instructions;
                    if (h.Model        is not null) entry["model"]        = h.Model;
                    hs.Add(entry);
                }
                cfg["handoffs"] = hs;
            }
            if (!string.IsNullOrEmpty(_outputType)) cfg["output_type"] = _outputType;
            if (cfg.Count > 0) agent.FrameworkConfig = cfg;

            return agent;
        }
    }
}
