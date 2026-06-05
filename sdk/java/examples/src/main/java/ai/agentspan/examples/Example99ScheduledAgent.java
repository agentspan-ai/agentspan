// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.schedule.Schedule;
import ai.agentspan.schedule.ScheduleInfo;

import java.util.List;
import java.util.Map;

/**
 * Example 99 — Scheduled Agent
 *
 * <p>Deploys an agent on two named cron schedules and exercises the full
 * lifecycle: list, pause, resume, run-now (ad-hoc), preview next fires,
 * and purge on cleanup.
 *
 * <p>Usage:
 * <pre>
 *   AGENTSPAN_SERVER_URL=http://localhost:6767/api \
 *   AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini \
 *   ./gradlew :examples:run -PmainClass=ai.agentspan.examples.Example99ScheduledAgent
 * </pre>
 */
public class Example99ScheduledAgent {

    public static void main(String[] args) throws Exception {
        String model = System.getenv().getOrDefault("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini");

        Agent agent = Agent.builder()
                .name("eng_digest_99")
                .model(model)
                .instructions(
                        "You are a concise engineering digest writer. " +
                        "Summarise recent activity for the channel in your input " +
                        "and return a short markdown bullet list (max 5 items).")
                .build();

        try (AgentRuntime runtime = new AgentRuntime()) {

            // 1. Deploy with two schedules.
            runtime.deploy(agent, List.of(
                    Schedule.builder()
                            .name("weekday-9am")
                            .cron("0 0 9 * * MON-FRI")
                            .timezone("America/Los_Angeles")
                            .input(Map.of("channel", "#eng"))
                            .description("Weekday morning digest")
                            .build(),
                    Schedule.builder()
                            .name("friday-5pm")
                            .cron("0 0 17 * * FRI")
                            .timezone("America/Los_Angeles")
                            .input(Map.of("channel", "#all-hands", "mode", "weekly"))
                            .description("Weekly all-hands digest")
                            .build()
            ));
            System.out.printf("✓ Deployed '%s' with 2 schedules%n", agent.getName());

            var sched = runtime.schedules();

            // 2. List schedules for this agent.
            List<ScheduleInfo> infos = sched.list(agent.getName());
            System.out.printf("%nSchedules (%d):%n", infos.size());
            for (ScheduleInfo s : infos) {
                System.out.printf("  %s  %s  [%s]%n",
                        s.getName(), s.getCron(), s.isPaused() ? "PAUSED" : "active");
            }

            if (infos.size() < 2) {
                System.err.println("Expected 2 schedules; aborting.");
                return;
            }

            String weekdayName = infos.stream()
                    .filter(s -> "weekday-9am".equals(s.getShortName()))
                    .findFirst().orElseThrow().getName();
            String fridayName = infos.stream()
                    .filter(s -> "friday-5pm".equals(s.getShortName()))
                    .findFirst().orElseThrow().getName();

            // 3. Pause the weekday schedule.
            sched.pause(weekdayName, "rate-limit cooldown demo");
            ScheduleInfo afterPause = sched.get(weekdayName);
            System.out.printf("%n✓ Paused '%s': paused=%b, reason=%s%n",
                    weekdayName, afterPause.isPaused(), afterPause.getPausedReason());

            // 4. Resume it.
            sched.resume(weekdayName);
            ScheduleInfo afterResume = sched.get(weekdayName);
            System.out.printf("✓ Resumed '%s': paused=%b%n", weekdayName, afterResume.isPaused());

            // 5. Ad-hoc run of the friday schedule.
            ScheduleInfo fridayInfo = sched.get(fridayName);
            String execId = sched.runNow(fridayInfo);
            System.out.printf("%n✓ runNow '%s' → execution id: %s%n", fridayName, execId);

            // 6. Preview next 5 fire times for the weekday cron.
            List<Long> nextFires = sched.previewNext("0 0 9 * * MON-FRI", 5);
            System.out.println("\nNext 5 fires for weekday-9am:");
            for (int i = 0; i < nextFires.size(); i++) {
                System.out.printf("  %d. %s%n", i + 1, new java.util.Date(nextFires.get(i)));
            }

            // 7. Cleanup: redeploy with empty list to purge all schedules.
            runtime.deploy(agent, List.of());
            System.out.printf("%n✓ Purged all schedules for '%s'%n", agent.getName());
        }
    }
}
