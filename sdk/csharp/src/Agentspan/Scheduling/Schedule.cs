// Copyright (c) 2026 Agentspan
// Licensed under the MIT License.

using System.Collections.Generic;

namespace Agentspan.Scheduling;

/// <summary>
/// A cron trigger attached to an agent. Mirrors <c>Schedule</c> in the Python /
/// TypeScript / Java SDKs. See <c>docs/design/scheduling.md</c>.
///
/// <para>
/// One agent can carry multiple schedules; each is identified by a <see cref="Name"/>
/// unique within that agent. The SDK auto-prefixes the wire name as
/// <c>{agent.Name}-{Name}</c> so Conductor's org-wide uniqueness is satisfied.
/// </para>
/// </summary>
public sealed class Schedule
{
    /// <summary>Short identifier, unique per agent. Required.</summary>
    public required string Name { get; init; }

    /// <summary>Cron expression — 6-field Quartz with seconds precision. Required.</summary>
    public required string Cron { get; init; }

    /// <summary>IANA timezone id; defaults to UTC.</summary>
    public string Timezone { get; init; } = "UTC";

    /// <summary>Workflow input passed when the cron fires.</summary>
    public IReadOnlyDictionary<string, object?> Input { get; init; }
        = new Dictionary<string, object?>();

    /// <summary>Replay missed fires on resume.</summary>
    public bool Catchup { get; init; }

    /// <summary>Start in paused state.</summary>
    public bool Paused { get; init; }

    /// <summary>Window start (epoch ms).</summary>
    public long? StartAt { get; init; }

    /// <summary>Window end (epoch ms).</summary>
    public long? EndAt { get; init; }

    /// <summary>Human-readable description.</summary>
    public string? Description { get; init; }

    public void Validate()
    {
        if (string.IsNullOrWhiteSpace(Name))
            throw new ScheduleException("Schedule.Name is required and must be non-empty");
        if (string.IsNullOrWhiteSpace(Cron))
            throw new ScheduleException("Schedule.Cron is required and must be non-empty");
        if (StartAt.HasValue && EndAt.HasValue && StartAt.Value >= EndAt.Value)
            throw new ScheduleException("Schedule.StartAt must be < EndAt");
    }
}

/// <summary>Server view of a schedule, as returned by <c>list/get</c>.</summary>
public sealed record ScheduleInfo(
    string Name,
    string ShortName,
    string Agent,
    string Cron,
    string Timezone,
    IReadOnlyDictionary<string, object?> Input,
    bool Paused,
    string? PausedReason,
    bool Catchup,
    long? StartAt,
    long? EndAt,
    string? Description,
    long? NextRun,
    long? CreateTime,
    long? UpdateTime,
    string? CreatedBy,
    string? UpdatedBy);
