// Copyright (c) 2025 AgentSpan
// Licensed under the MIT License.
//
// Deterministic concurrent-injection contract test.
//
// See docs/design/secret-injection-contract.md §5 — every SDK with framework
// passthrough must have a paired test:
//   (1) counterfactual that proves the naive pattern races
//   (2) fix-verification that proves the helper isolates concurrent calls
//
// Both use a Barrier / ManualResetEventSlim to force the race deterministically
// — no sleeps, no retries, no flake.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Agentspan;
using Xunit;

namespace AgentspanE2eTests;

public class SecretInjectionConcurrentTest
{
    private const string KEY = "_AS_TEST_RACE_KEY_DOTNET";

    // ── Counterfactual: the buggy pattern races ───────────────────────────────

    /// <summary>
    /// The naive pattern — mutate env, invoke, restore — with no lock.
    /// Kept here as a counterfactual.
    /// </summary>
    private static async Task<T> BuggyInjectAsync<T>(
        IReadOnlyDictionary<string, string> secrets,
        Func<Task<T>> invoke)
    {
        var injected = new List<string>();
        try
        {
            foreach (var kv in secrets)
            {
                Environment.SetEnvironmentVariable(kv.Key, kv.Value);
                injected.Add(kv.Key);
            }
            return await invoke().ConfigureAwait(false);
        }
        finally
        {
            foreach (var k in injected)
                Environment.SetEnvironmentVariable(k, null);
        }
    }

    [Fact]
    public async Task BuggyInjection_RacesDeterministically()
    {
        // Step order forced by the barrier: both threads enter their fake_invoke
        // before either reads env. Whichever wrote env most recently wins; the
        // other thread sees the WRONG value (or null if its own pop ran first).

        var barrier = new Barrier(2);
        string? aObserved = null;
        string? bObserved = null;

        Task<string> WorkerAsync(string value, Action<string?> recordObservation)
        {
            return BuggyInjectAsync(
                new Dictionary<string, string> { [KEY] = value },
                () =>
                {
                    barrier.SignalAndWait(TimeSpan.FromSeconds(5));
                    recordObservation(Environment.GetEnvironmentVariable(KEY));
                    return Task.FromResult("ok");
                });
        }

        var ta = WorkerAsync("A", v => aObserved = v);
        var tb = WorkerAsync("B", v => bObserved = v);
        await Task.WhenAll(ta, tb);

        // COUNTERFACTUAL ASSERTION: at least one thread observed a clobbered value.
        // Failure modes: both see latest writer, or one sees null because the
        // other's `finally` already popped the key. Either way, at least one
        // observation is wrong.
        bool aCorrect = aObserved == "A";
        bool bCorrect = bObserved == "B";
        Assert.False(aCorrect && bCorrect,
            $"Counterfactual expected at least one thread to observe a clobbered " +
            $"env value, but both saw their own. Got A={aObserved ?? "null"}, " +
            $"B={bObserved ?? "null"}. If the buggy pattern is no longer racing, " +
            $"investigate before deleting this test.");
    }

    // ── Fix verification: SecretInjection.InjectViaEnvAsync isolates ──────────

    [Fact]
    public async Task FixedInjection_IsolatesConcurrentCalls()
    {
        // With the lock spanning the whole invocation, A's view of env never
        // changes while A is running. B's invocation can't begin until A is done.

        var aObservations = new List<string?>();
        var bObservations = new List<string?>();
        var aInside = new ManualResetEventSlim(false);
        var aCanFinish = new ManualResetEventSlim(false);

        Task<string> WorkerA() =>
            SecretInjection.InjectViaEnvAsync(
                new Dictionary<string, string> { [KEY] = "A" },
                async () =>
                {
                    aObservations.Add(Environment.GetEnvironmentVariable(KEY));
                    aInside.Set();
                    // Hold here so B has time to try (and fail) to enter the lock.
                    aCanFinish.Wait(TimeSpan.FromSeconds(5));
                    aObservations.Add(Environment.GetEnvironmentVariable(KEY));
                    await Task.Yield();
                    return "ok";
                });

        Task<string> WorkerB() =>
            SecretInjection.InjectViaEnvAsync(
                new Dictionary<string, string> { [KEY] = "B" },
                () =>
                {
                    bObservations.Add(Environment.GetEnvironmentVariable(KEY));
                    return Task.FromResult("ok");
                });

        var ta = Task.Run(WorkerA);
        Assert.True(aInside.Wait(TimeSpan.FromSeconds(5)),
            "Worker A never entered its invoke.");
        var tb = Task.Run(WorkerB);   // will block on the lock until A releases
        await Task.Delay(100);        // give B time to attempt entry
        aCanFinish.Set();
        await Task.WhenAll(ta, tb);

        // FIX ASSERTION 1: A's view was stable across the whole invocation.
        Assert.Equal(new[] { "A", "A" }, aObservations);

        // FIX ASSERTION 2: B saw its own value after acquiring the lock.
        Assert.Equal(new[] { "B" }, bObservations);

        // FIX ASSERTION 3: env was restored to its pre-call state.
        Assert.Null(Environment.GetEnvironmentVariable(KEY));
    }

    [Fact]
    public async Task FixedInjection_RestoresPreexistingValue()
    {
        Environment.SetEnvironmentVariable(KEY, "pre-existing");
        try
        {
            await SecretInjection.InjectViaEnvAsync(
                new Dictionary<string, string> { [KEY] = "injected" },
                () =>
                {
                    Assert.Equal("injected", Environment.GetEnvironmentVariable(KEY));
                    return Task.FromResult(0);
                });

            Assert.Equal("pre-existing", Environment.GetEnvironmentVariable(KEY));
        }
        finally
        {
            Environment.SetEnvironmentVariable(KEY, null);
        }
    }

    [Fact]
    public async Task FixedInjection_RestoresOnException()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            SecretInjection.InjectViaEnvAsync<int>(
                new Dictionary<string, string> { [KEY] = "should-cleanup" },
                () => throw new InvalidOperationException("boom")));

        Assert.Null(Environment.GetEnvironmentVariable(KEY));
    }
}
