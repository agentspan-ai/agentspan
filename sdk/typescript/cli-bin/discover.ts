import { readdirSync } from 'fs';
import { join, extname } from 'path';
import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { Agent } from '../src/agent.js';
import { detectFramework } from '../src/frameworks/detect.js';

export interface DiscoveryEntry {
  name: string;
  framework: string;
}

export function formatDiscoveryResult(agents: { obj: unknown; name: string; framework: string }[]): DiscoveryEntry[] {
  return agents.map(a => ({ name: a.name, framework: a.framework }));
}

/**
 * Scan a directory for .ts/.js files and discover all agent-like exports,
 * including native AgentSpan agents and framework agents (OpenAI, ADK,
 * LangChain, LangGraph).
 */
async function discoverAllAgents(scanPath: string): Promise<{ obj: unknown; name: string; framework: string }[]> {
  const entries = readdirSync(scanPath, { withFileTypes: true });
  const found: { obj: unknown; name: string; framework: string }[] = [];
  const seenNames = new Set<string>();

  for (const entry of entries) {
    if (!entry.isFile()) continue;
    const ext = extname(entry.name);
    if (ext !== '.ts' && ext !== '.js') continue;
    if (entry.name.startsWith('_')) continue;

    const fullPath = join(scanPath, entry.name);
    try {
      const mod = await import(fullPath);
      for (const exportValue of Object.values(mod)) {
        if (exportValue == null || typeof exportValue !== 'object') continue;

        const isNative = exportValue instanceof Agent;
        const frameworkId = isNative ? null : detectFramework(exportValue);

        if (isNative || frameworkId) {
          const name = (exportValue as any).name;
          if (name && typeof name === 'string' && !seenNames.has(name)) {
            seenNames.add(name);
            found.push({
              obj: exportValue,
              name,
              framework: frameworkId ?? 'native',
            });
          }
        }
      }
    } catch {
      // Skip files that fail to import
    }
  }

  return found;
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

  try {
    // Redirect stdout → stderr during imports so that console.log()
    // side-effects in imported files don't corrupt our JSON output.
    const realStdoutWrite = process.stdout.write.bind(process.stdout);
    process.stdout.write = process.stderr.write.bind(process.stderr);

    const agents = await discoverAllAgents(resolve(values.path as string));

    // Restore stdout for our JSON output
    process.stdout.write = realStdoutWrite;

    const result = formatDiscoveryResult(agents);
    console.log(JSON.stringify(result));
  } catch (e: any) {
    console.error(`Discovery failed: ${e.message || e}`);
    process.exit(1);
  }
}

const isMain = process.argv[1]?.endsWith('discover.ts') || process.argv[1]?.endsWith('discover.js');
if (isMain) {
  main();
}
