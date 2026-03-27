import { readdirSync } from 'fs';
import { join, extname } from 'path';
import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { Agent } from '../src/agent.js';
import { deploy } from '../src/runtime.js';
import { detectFramework } from '../src/frameworks/detect.js';
import type { DeploymentInfo } from '../src/types.js';

export interface DeployResultEntry {
  agent_name: string;
  workflow_name: string | null;
  success: boolean;
  error: string | null;
}

export function filterAgents<T extends { name: string }>(agents: T[], agentsFlag: string | undefined): T[] {
  if (!agentsFlag) return agents;
  const names = new Set(agentsFlag.split(','));
  return agents.filter(a => names.has(a.name));
}

export function formatDeployResult(
  agentName: string,
  info: DeploymentInfo | null,
  error: string | null,
): DeployResultEntry {
  if (info) {
    return {
      agent_name: agentName,
      workflow_name: info.workflowName,
      success: true,
      error: null,
    };
  }
  return {
    agent_name: agentName,
    workflow_name: null,
    success: false,
    error,
  };
}

/**
 * Discover all agent-like exports (native + framework) from a directory.
 */
async function discoverAllAgents(scanPath: string): Promise<{ obj: unknown; name: string }[]> {
  const entries = readdirSync(scanPath, { withFileTypes: true });
  const found: { obj: unknown; name: string }[] = [];
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
            found.push({ obj: exportValue, name });
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
    options: {
      path: { type: 'string' },
      agents: { type: 'string' },
    },
    strict: false,
  });

  if (!values.path) {
    console.error('Error: --path is required');
    process.exit(1);
  }

  // Redirect stdout → stderr during imports so that console.log()
  // side-effects in imported files don't corrupt our JSON output.
  const realStdoutWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = process.stderr.write.bind(process.stderr);

  let agents: { obj: unknown; name: string }[];
  try {
    agents = await discoverAllAgents(resolve(values.path as string));
  } catch (e: any) {
    console.error(`Discovery failed: ${e.message || e}`);
    process.exit(1);
  }

  agents = filterAgents(agents, values.agents as string | undefined);

  const results: DeployResultEntry[] = [];

  for (const agent of agents) {
    try {
      const info = await deploy(agent.obj as any);
      results.push(formatDeployResult(agent.name, info, null));
    } catch (e: any) {
      const errMsg = e.message || String(e);
      results.push(formatDeployResult(agent.name, null, errMsg));
      console.error(`Deploy failed for ${agent.name}: ${errMsg}`);
    }
  }

  // Restore stdout for our JSON output
  process.stdout.write = realStdoutWrite;
  console.log(JSON.stringify(results));
}

const isMain = process.argv[1]?.endsWith('deploy.ts') || process.argv[1]?.endsWith('deploy.js');
if (isMain) {
  main();
}
