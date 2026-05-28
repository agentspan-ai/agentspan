// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.schedule;

import java.util.Map;

/** Server view of a schedule, returned by {@link Schedules#list(String)} / {@link Schedules#get(String)}. */
public final class ScheduleInfo {
    private final String name;
    private final String shortName;
    private final String agent;
    private final String cron;
    private final String timezone;
    private final Map<String, Object> input;
    private final boolean paused;
    private final String pausedReason;
    private final boolean catchup;
    private final Long startAt;
    private final Long endAt;
    private final String description;
    private final Long nextRun;
    private final Long createTime;
    private final Long updateTime;
    private final String createdBy;
    private final String updatedBy;

    public ScheduleInfo(
            String name, String shortName, String agent, String cron, String timezone,
            Map<String, Object> input, boolean paused, String pausedReason, boolean catchup,
            Long startAt, Long endAt, String description, Long nextRun,
            Long createTime, Long updateTime, String createdBy, String updatedBy) {
        this.name = name;
        this.shortName = shortName;
        this.agent = agent;
        this.cron = cron;
        this.timezone = timezone;
        this.input = input;
        this.paused = paused;
        this.pausedReason = pausedReason;
        this.catchup = catchup;
        this.startAt = startAt;
        this.endAt = endAt;
        this.description = description;
        this.nextRun = nextRun;
        this.createTime = createTime;
        this.updateTime = updateTime;
        this.createdBy = createdBy;
        this.updatedBy = updatedBy;
    }

    public String getName() { return name; }
    public String getShortName() { return shortName; }
    public String getAgent() { return agent; }
    public String getCron() { return cron; }
    public String getTimezone() { return timezone; }
    public Map<String, Object> getInput() { return input; }
    public boolean isPaused() { return paused; }
    public String getPausedReason() { return pausedReason; }
    public boolean isCatchup() { return catchup; }
    public Long getStartAt() { return startAt; }
    public Long getEndAt() { return endAt; }
    public String getDescription() { return description; }
    public Long getNextRun() { return nextRun; }
    public Long getCreateTime() { return createTime; }
    public Long getUpdateTime() { return updateTime; }
    public String getCreatedBy() { return createdBy; }
    public String getUpdatedBy() { return updatedBy; }

    @Override
    public String toString() {
        return "ScheduleInfo{name=" + name + ", agent=" + agent + ", cron=" + cron + ", paused=" + paused + "}";
    }
}
