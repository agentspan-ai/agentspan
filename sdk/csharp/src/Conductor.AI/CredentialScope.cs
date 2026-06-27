// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.
//
// Tier-1 credential accessor. The worker populates an AsyncLocal credential
// scope immediately before invoking each tool; tool code reads resolved
// credentials via ToolContext.GetCredential / Secrets.Get without any process
// environment mutation (tier-2). Mirrors Java ToolContext.getCredential
// (backed by internal.CredentialContext ThreadLocal) and TS getCredential
// (AsyncLocalStorage).

using System.Threading;

namespace Conductor.AI;

/// <summary>
/// An ambient, flow-local scope of resolved credentials. The worker wraps each
/// tool invocation in a scope; tool code reads credentials via
/// <see cref="ToolContext.GetCredential"/> or <see cref="Secrets.Get"/>.
/// Backed by <see cref="AsyncLocal{T}"/> so concurrent tool invocations in the
/// same process do not see each other's credentials.
/// </summary>
public sealed class CredentialScope : IDisposable
{
    private static readonly AsyncLocal<IReadOnlyDictionary<string, string>?> s_current = new();

    private readonly IReadOnlyDictionary<string, string>? _previous;
    private bool _disposed;

    private CredentialScope(IReadOnlyDictionary<string, string> credentials)
    {
        _previous = s_current.Value;
        s_current.Value = credentials;
    }

    /// <summary>The credentials visible in the current async flow, or <c>null</c>.</summary>
    internal static IReadOnlyDictionary<string, string>? Current => s_current.Value;

    /// <summary>
    /// Begin a credential scope for the current async flow. Dispose to restore
    /// the previous scope.
    /// </summary>
    public static CredentialScope Begin(IReadOnlyDictionary<string, string> credentials)
        => new(credentials ?? new Dictionary<string, string>());

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        s_current.Value = _previous;
    }
}

/// <summary>
/// Convenience accessor for credentials resolved by the worker for the current
/// tool invocation. Equivalent to <see cref="ToolContext.GetCredential"/>.
/// </summary>
public static class Secrets
{
    /// <summary>
    /// Return the resolved value of credential <paramref name="name"/> for the
    /// current tool invocation, or <c>null</c> if not present / outside a scope.
    /// </summary>
    public static string? Get(string name)
        => CredentialScope.Current is { } creds && creds.TryGetValue(name, out var v) ? v : null;
}
