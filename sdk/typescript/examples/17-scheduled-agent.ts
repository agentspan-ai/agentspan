/**
 * Scheduled Agent — deploy an agent on a cron schedule.
 *
 * Demonstrates the declarative schedule API: attach one or more named cron
 * schedules to an agent at deploy time, then use the schedules namespace to
 * inspect, pause, resume, and run-now without writing any boilerplate.
 *
 * Flow:
 *   1. Define a lightweight digest agent (no real LLM call needed here).
 *   2. Deploy with two schedules — weekday 9 AM and Friday 5 PM.
 *   3. List the schedules back to confirm they were registered.
 *   4. Pause one schedule; verify paused state.
 *   5. Resume it; verify active state.
 *   6. Fire ad-hoc with runNow; capture execution id.
 *   7. Preview next 5 fire times for the cron.
 *   8. Redeploy with an empty list to purge all schedules (cleanup).
 *
 * Requirements:
 *   - Conductor server at AGENTSPAN_SERVER_URL (default: http://localhost:6767/api)
 *   - Scheduler module enabled (on by default)
 *
 * Run:
 *   AGENTSPAN_SERVER_URL=http://localhost:6767/api \
 *   npx ts-node examples/17-scheduled-agent.ts
 */

import { Agent, AgentRuntime, Schedule, schedules } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// -- Agent definition --------------------------------------------------------

const digestAgent = new Agent({
  name: 'eng_digest_17',
  model: llmModel,
  instructions:
    'You are a concise engineering digest writer. ' +
    'Summarise recent activity for the channel provided in your input and ' +
    'return a short markdown bullet list (max 5 items).',
});

// -- Main --------------------------------------------------------------------

async function main() {
  await using const runtime = new AgentRuntime();

  // 1. Deploy with two named schedules.
  await runtime.deploy(digestAgent, {
    schedules: [
      new Schedule({
        name: 'weekday-9am',
        cron: '0 0 9 * * MON-FRI',
        timezone: 'America/Los_Angeles',
        input: { channel: '#eng' },
        description: 'Weekday morning digest',
      }),
      new Schedule({
        name: 'friday-5pm',
        cron: '0 0 17 * * FRI',
        timezone: 'America/Los_Angeles',
        input: { channel: '#all-hands', mode: 'weekly' },
        description: 'Weekly all-hands digest',
      }),
    ],
  });
  console.log(`✓ Deployed '${digestAgent.name}' with 2 schedules`);

  // 2. List schedules for this agent.
  const infos = await schedules.list({ agent: digestAgent.name });
  console.log(`\nSchedules (${infos.length}):`);
  for (const s of infos) {
    const status = s.paused ? 'PAUSED' : 'active';
    console.log(`  ${s.name}  ${s.cron}  [${status}]  next: ${s.nextRunTime ?? '—'}`);
  }

  if (infos.length < 2) {
    console.error('Expected 2 schedules; aborting.');
    return;
  }

  const weekdayName = infos.find((s) => s.shortName === 'weekday-9am')!.name;
  const fridayName  = infos.find((s) => s.shortName === 'friday-5pm')!.name;

  // 3. Pause the weekday schedule.
  await schedules.pause(weekdayName, { reason: 'rate-limit cooldown demo' });
  const afterPause = await schedules.get(weekdayName);
  console.log(`\n✓ Paused '${weekdayName}': paused=${afterPause.paused}, reason=${afterPause.pausedReason}`);

  // 4. Resume it.
  await schedules.resume(weekdayName);
  const afterResume = await schedules.get(weekdayName);
  console.log(`✓ Resumed '${weekdayName}': paused=${afterResume.paused}`);

  // 5. Ad-hoc run of the friday schedule.
  const execId = await schedules.runNow(fridayName);
  console.log(`\n✓ runNow '${fridayName}' → execution id: ${execId}`);

  // 6. Preview next fire times for the weekday cron.
  const nextFires = await schedules.previewNext('0 0 9 * * MON-FRI', { n: 5 });
  console.log('\nNext 5 fires for weekday-9am:');
  nextFires.forEach((t, i) => console.log(`  ${i + 1}. ${new Date(t).toISOString()}`));

  // 7. Cleanup: redeploy with no schedules to purge both.
  await runtime.deploy(digestAgent, { schedules: [] });
  console.log(`\n✓ Purged all schedules for '${digestAgent.name}'`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
