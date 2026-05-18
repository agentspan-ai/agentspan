import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { discoverAllAgents } from './shared.js';
import type { DiscoveredAgent } from './shared.js';

export interface DiscoveryEntry {
  name: string;
  framework: string;
}

export function formatDiscoveryResult(agents: { obj: unknown; name: string; framework: string }[]): DiscoveryEntry[] {
  return agents.map(a => ({ name: a.name, framework: a.framework }));
}

async function main() {
  const { values } = parseArgs({
    options: { path: { type: 'string' } },
    strict: false,
  });

  if (!values.path) {
    console.error('Error: --path is required');
    process.exit(1);
  }

  // Redirect stdout -> stderr during imports so that console.log()
  // side-effects in imported files don't corrupt our JSON output.
  const realStdoutWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = process.stderr.write.bind(process.stderr);

  try {
    const agents = await discoverAllAgents(resolve(values.path as string));

    // Restore stdout for our JSON output
    process.stdout.write = realStdoutWrite;

    const result = formatDiscoveryResult(agents);
    console.log(JSON.stringify(result));
  } catch (e: any) {
    // Restore stdout before error handling
    process.stdout.write = realStdoutWrite;
    console.error(`Discovery failed: ${e.message || e}`);
    process.exit(1);
  }
}

const isMain = process.argv[1]?.endsWith('discover.ts') || process.argv[1]?.endsWith('discover.js');
if (isMain) {
  main();
}
