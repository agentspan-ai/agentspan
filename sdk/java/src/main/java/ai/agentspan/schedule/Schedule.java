// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.schedule;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * A cron trigger attached to an agent. Mirrors {@code Schedule} in the Python /
 * TypeScript SDKs. See {@code docs/design/scheduling.md}.
 *
 * <p>One agent can carry multiple schedules; each is identified by a {@code name}
 * unique within that agent. The SDK auto-prefixes the wire name as
 * {@code {agent.name}-{name}} so Conductor's org-wide uniqueness is satisfied.
 *
 * <p>Construct via {@link #builder()}.
 */
public final class Schedule {

    private final String name;
    private final String cron;
    private final String timezone;
    private final Map<String, Object> input;
    private final boolean catchup;
    private final boolean paused;
    private final Long startAt;
    private final Long endAt;
    private final String description;

    private Schedule(Builder b) {
        if (b.name == null || b.name.trim().isEmpty()) {
            throw new ScheduleException("Schedule.name is required and must be non-empty");
        }
        if (b.cron == null || b.cron.trim().isEmpty()) {
            throw new ScheduleException("Schedule.cron is required and must be non-empty");
        }
        if (b.startAt != null && b.endAt != null && b.startAt >= b.endAt) {
            throw new ScheduleException("Schedule.startAt must be < endAt");
        }
        this.name = b.name;
        this.cron = b.cron;
        this.timezone = b.timezone != null ? b.timezone : "UTC";
        this.input = b.input == null ? Collections.emptyMap() : new LinkedHashMap<>(b.input);
        this.catchup = b.catchup;
        this.paused = b.paused;
        this.startAt = b.startAt;
        this.endAt = b.endAt;
        this.description = b.description;
    }

    public static Builder builder() { return new Builder(); }

    public String getName() { return name; }
    public String getCron() { return cron; }
    public String getTimezone() { return timezone; }
    public Map<String, Object> getInput() { return input; }
    public boolean isCatchup() { return catchup; }
    public boolean isPaused() { return paused; }
    public Long getStartAt() { return startAt; }
    public Long getEndAt() { return endAt; }
    public String getDescription() { return description; }

    public static final class Builder {
        private String name;
        private String cron;
        private String timezone;
        private Map<String, Object> input;
        private boolean catchup;
        private boolean paused;
        private Long startAt;
        private Long endAt;
        private String description;

        public Builder name(String v)         { this.name = v; return this; }
        public Builder cron(String v)         { this.cron = v; return this; }
        public Builder timezone(String v)     { this.timezone = v; return this; }
        public Builder input(Map<String, Object> v) { this.input = v; return this; }
        public Builder catchup(boolean v)     { this.catchup = v; return this; }
        public Builder paused(boolean v)      { this.paused = v; return this; }
        public Builder startAt(Long v)        { this.startAt = v; return this; }
        public Builder endAt(Long v)          { this.endAt = v; return this; }
        public Builder description(String v)  { this.description = v; return this; }
        public Schedule build() { return new Schedule(this); }
    }
}
