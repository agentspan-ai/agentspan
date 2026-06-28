// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.schedule;

/** Base class for schedule errors. */
public class ScheduleException extends RuntimeException {
    public ScheduleException(String message) {
        super(message);
    }

    public ScheduleException(String message, Throwable cause) {
        super(message, cause);
    }

    /** Two schedules in the same agent share a name. */
    public static class NameConflict extends ScheduleException {
        public NameConflict(String message) {
            super(message);
        }
    }

    /** No schedule matches the given name. */
    public static class NotFound extends ScheduleException {
        public NotFound(String message) {
            super(message);
        }
    }

    /** Server rejected the cron expression as malformed. */
    public static class InvalidCron extends ScheduleException {
        public InvalidCron(String message) {
            super(message);
        }
    }

    /** A {@code runNow(..., wait=true)} workflow did not finish within the timeout. */
    public static class Timeout extends ScheduleException {
        public Timeout(String message) {
            super(message);
        }
    }
}
