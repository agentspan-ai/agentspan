// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

namespace Agentspan;

/// <summary>How the user proxy requests human input.</summary>
public enum HumanInputMode
{
    /// <summary>Always pause for human input.</summary>
    Always,
    /// <summary>Pause only when the conversation would otherwise end.</summary>
    Terminate,
    /// <summary>Never pause — use <see cref="UserProxyAgent.Create"/>'s default response.</summary>
    Never,
}

/// <summary>
/// Factory for creating a user-proxy agent — a human stand-in in multi-agent conversations.
///
/// When it is the proxy's turn the workflow pauses with a <see cref="EventType.Waiting"/> event
/// and waits for input via <see cref="AgentHandle.RespondAsync"/>.
/// </summary>
public static class UserProxyAgent
{
    /// <summary>
    /// Create an agent that acts as a stand-in for a human user.
    /// </summary>
    /// <param name="name">Agent name (default <c>"user"</c>).</param>
    /// <param name="humanInputMode">When to pause for human input (default Always).</param>
    /// <param name="defaultResponse">Response when mode is <see cref="HumanInputMode.Never"/>.</param>
    /// <param name="model">LLM model (used only if the agent needs to generate a response).</param>
    /// <param name="instructions">System instructions (optional).</param>
    public static Agent Create(
        string           name             = "user",
        HumanInputMode   humanInputMode   = HumanInputMode.Always,
        string           defaultResponse  = "Continue.",
        string?          model            = null,
        string?          instructions     = null)
    {
        var modeStr = humanInputMode switch
        {
            HumanInputMode.Always    => "ALWAYS",
            HumanInputMode.Terminate => "TERMINATE",
            HumanInputMode.Never     => "NEVER",
            _                        => "ALWAYS",
        };

        return new Agent(name)
        {
            Model        = model ?? "openai/gpt-4o-mini",
            Instructions = instructions
                ?? "You represent the human user in this conversation. Relay the human's input exactly as provided.",
            Metadata = new Dictionary<string, object>
            {
                ["_agent_type"]         = "user_proxy",
                ["_human_input_mode"]   = modeStr,
                ["_default_response"]   = defaultResponse,
            },
        };
    }
}
