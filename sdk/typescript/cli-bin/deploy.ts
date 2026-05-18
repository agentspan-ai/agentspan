import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { deploy } from '../src/runtime.js';
import { discoverAllAgents } from './shared.js';
import type { DeploymentInfo } from '../src/types.js';

export interface DeployResultEntry {
  agent_name: string;
  workflow_name: string | null;
  success: boolean;
  error: string | null;
}

export function filterAgents<T extends { name: string }>(agents: T[], agentsFlag: string | undefined): T[] {
  if (!agentsFlag) return agents;
  const names = new Set(agentsFlag.split(',').map(s => s.trim()).filter(Boolean));
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

  // Redirect stdout -> stderr during imports so that console.log()
  // side-effects in imported files don't corrupt our JSON output.
  const realStdoutWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = process.stderr.write.bind(process.stderr);

  try {
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
  } catch (e: any) {
    // Restore stdout before error handling
    process.stdout.write = realStdoutWrite;
    console.error(`Deploy failed: ${e.message || e}`);
    process.exit(1);
  }
}

const isMain = process.argv[1]?.endsWith('deploy.ts') || process.argv[1]?.endsWith('deploy.js');
if (isMain) {
  main();
}
