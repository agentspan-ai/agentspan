// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License.
//
// Secret injection for framework passthrough — concurrency-safe.
//
// Implements the SDK contract documented in
// docs/design/secret-injection-contract.md. The naive
// "SetEnvironmentVariable, invoke, restore" pattern is unsafe under
// concurrency because the process environment is shared across all threads.
//
// Tier 2 (env injection, this file): holds a process-wide async lock across
// mutation + invocation + restoration so concurrent framework workers serialize
// instead of clobbering each other. Strictly serial within one worker process;
// scale by adding worker processes.
//
// Tier 1 (explicit-key passthrough): users pass resolved credentials directly into
// their framework's model client (e.g. `new OpenAIClient(apiKey: credentials["..."])`).
// No lock, fully concurrent. The user-facing API change lands in a future PR.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Agentspan
{
    /// <summary>
    /// Concurrency-safe injection of resolved credentials into the process
    /// environment for the duration of a single framework invocation.
    /// </summary>
    public static class CredentialInjection
    {
        // ONE process-wide semaphore. All tier-2 framework workers in this
        // process contend for it. Tier-1 (explicit-key) paths must NOT acquire it.
        private static readonly SemaphoreSlim s_envInjectionLock = new(1, 1);

        /// <summary>
        /// Run <paramref name="invoke"/> with <paramref name="credentials"/> injected
        /// into <c>Environment</c> for the duration of the call. Mutation,
        /// invocation, and restoration happen atomically under a process-wide
        /// lock — concurrent callers serialize.
        /// </summary>
        /// <returns>Whatever <paramref name="invoke"/> returns.</returns>
        public static async Task<T> InjectViaEnvAsync<T>(
            IReadOnlyDictionary<string, string> credentials,
            Func<Task<T>> invoke,
            CancellationToken ct = default)
        {
            if (credentials == null || credentials.Count == 0)
                return await invoke().ConfigureAwait(false);

            await s_envInjectionLock.WaitAsync(ct).ConfigureAwait(false);
            try
            {
                var previous = new Dictionary<string, string?>(credentials.Count);
                foreach (var kv in credentials)
                {
                    previous[kv.Key] = Environment.GetEnvironmentVariable(kv.Key);
                    Environment.SetEnvironmentVariable(kv.Key, kv.Value);
                }
                try
                {
                    return await invoke().ConfigureAwait(false);
                }
                finally
                {
                    foreach (var kv in previous)
                        Environment.SetEnvironmentVariable(kv.Key, kv.Value);
                }
            }
            finally
            {
                s_envInjectionLock.Release();
            }
        }
    }
}
