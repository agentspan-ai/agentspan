// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

namespace Agentspan;

/// <summary>Base exception for all Agentspan errors.</summary>
public class AgentspanException : Exception
{
    public AgentspanException(string message) : base(message) { }
    public AgentspanException(string message, Exception inner) : base(message, inner) { }
}

/// <summary>Server returned an HTTP error.</summary>
public class AgentApiException : AgentspanException
{
    public int StatusCode { get; }
    public string? ResponseBody { get; }

    public AgentApiException(int statusCode, string message, string? body = null)
        : base($"API error {statusCode}: {message}")
    {
        StatusCode = statusCode;
        ResponseBody = body;
    }
}

/// <summary>Invalid agent configuration.</summary>
public class ConfigurationException : AgentspanException
{
    public ConfigurationException(string message) : base(message) { }
}

/// <summary>Agent not found on server.</summary>
public class AgentNotFoundException : AgentspanException
{
    public string AgentName { get; }
    public AgentNotFoundException(string agentName)
        : base($"Agent not found: {agentName}") => AgentName = agentName;
}

/// <summary>Credential not found in the credential store.</summary>
public class CredentialNotFoundException : AgentspanException
{
    public string CredentialName { get; }
    public CredentialNotFoundException(string name)
        : base($"Credential not found: {name}") => CredentialName = name;
}

/// <summary>Credential authentication failed.</summary>
public class CredentialAuthException : AgentspanException
{
    public CredentialAuthException(string message) : base(message) { }
}

/// <summary>Credential service rate limit exceeded.</summary>
public class CredentialRateLimitException : AgentspanException
{
    public CredentialRateLimitException()
        : base("Credential service rate limit exceeded.") { }
}

/// <summary>Credential service returned a server error.</summary>
public class CredentialServiceException : AgentspanException
{
    public CredentialServiceException(string message) : base(message) { }
}

/// <summary>
/// Tool threw a terminal (non-retryable) error.
/// Maps to Conductor's FAILED_WITH_TERMINAL_ERROR status.
/// </summary>
public class TerminalToolException : AgentspanException
{
    public TerminalToolException(string message) : base(message) { }
    public TerminalToolException(string message, Exception inner) : base(message, inner) { }
}
