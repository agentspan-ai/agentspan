// Copyright (c) 2026 Agentspan
// Licensed under the MIT License.

namespace Agentspan.Scheduling;

public class ScheduleException : Exception
{
    public ScheduleException(string message) : base(message) { }
    public ScheduleException(string message, Exception inner) : base(message, inner) { }
}

public sealed class ScheduleNameConflict : ScheduleException
{
    public ScheduleNameConflict(string message) : base(message) { }
}

public sealed class ScheduleNotFound : ScheduleException
{
    public ScheduleNotFound(string message) : base(message) { }
}

public sealed class InvalidCronExpression : ScheduleException
{
    public InvalidCronExpression(string message) : base(message) { }
}
