/**
 * Harness: serialize one LangGraph example and output worker count as JSON.
 * Usage: npx tsx tests/_worker-harness.ts <example-file-path>
 *
 * Because the package root and node_modules may hold separate copies of
 * @agentspan-ai/sdk (different inodes), we must patch AgentRuntime.prototype
 * on BOTH copies so the dynamically-imported example always hits our stub.
 */
import { serializeLangGraph } from '../src/frameworks/langgraph-serializer.js';
import { serializeFrameworkAgent } from '../src/frameworks/serializer.js';
import { detectFramework } from '../src/frameworks/detect.js';
import { join } from 'path';
import { existsSync } from 'fs';
import { pathToFileURL } from 'url';

const examplePath = process.argv[2];
if (!examplePath) {
  process.stdout.write(JSON.stringify({ error: 'no file path' }) + '\n');
  process.exit(1);
}

let captured: [Record<string, unknown>, any[]] | null = null;

// Helper: patch an AgentRuntime class (prototype)
function patchRuntime(RT: any) {
  RT.prototype.run = async function (agent: any) {
    const fw = detectFramework(agent);
    if (fw === 'langgraph') {
      try { captured = serializeLangGraph(agent); } catch {}
    } else if (fw) {
      try { captured = serializeFrameworkAgent(agent); } catch {}
    }
    return {
      status: 'COMPLETED', output: {}, events: [], messages: [], toolCalls: [],
      isSuccess: true, isFailed: false, isRejected: false, finishReason: 'stop',
      executionId: '', printResult() {},
    };
  };
  RT.prototype.plan = async function (agent: any) {
    const fw = detectFramework(agent);
    if (fw === 'langgraph') {
      try { captured = serializeLangGraph(agent); } catch {}
    } else if (fw) {
      try { captured = serializeFrameworkAgent(agent); } catch {}
    }
    return {};
  };
  RT.prototype.shutdown = async function () {};
  RT.prototype.serve = async function (...agents: any[]) {
    for (const agent of agents) {
      const fw = detectFramework(agent);
      if (fw === 'langgraph') {
        try { captured = serializeLangGraph(agent); } catch {}
      } else if (fw) {
        try { captured = serializeFrameworkAgent(agent); } catch {}
      }
    }
  };
}

// Collect all patched AgentRuntime classes to avoid double-patching
const patched = new Set<unknown>();

function patchIfNew(RT: unknown) {
  if (RT && typeof RT === 'function' && !patched.has(RT)) {
    patched.add(RT);
    patchRuntime(RT);
  }
}

// 1) Patch the self-reference copy (root dist)
const selfPkg = await import('@agentspan-ai/sdk');
patchIfNew(selfPkg.AgentRuntime);

// 2) Patch the node_modules copy if it exists and is a different module
const nmDistPath = join(process.cwd(), 'node_modules', '@agentspan-ai', 'sdk', 'dist', 'index.js');
if (existsSync(nmDistPath)) {
  try {
    const nmPkg = await import(pathToFileURL(nmDistPath).href);
    patchIfNew(nmPkg.AgentRuntime);
  } catch {}
}

// 3) Patch the source copy (examples' tsconfig maps @agentspan-ai/sdk to ../src/index.ts)
try {
  const srcPkg = await import('../src/index.js');
  patchIfNew(srcPkg.AgentRuntime);
} catch {}

// Suppress example console output but not stderr
console.log = () => {};
console.warn = () => {};

// Set env vars so AgentRuntime constructor doesn't fail
process.env.AGENTSPAN_SERVER_URL ??= 'http://localhost:6767/api';
process.env.OPENAI_API_KEY ??= 'sk-fake';
process.env.ANTHROPIC_API_KEY ??= 'sk-fake';
process.env.GOOGLE_API_KEY ??= 'fake';

// Set process.argv[1] to the example path so the example's
// `if (process.argv[1]?.endsWith(...))` guard passes and main() runs.
const originalArgv1 = process.argv[1];
process.argv[1] = examplePath;

try {
  await import(examplePath);
  await new Promise(r => setTimeout(r, 2000));
} catch {} finally {
  process.argv[1] = originalArgv1;
}

// Output result
const write = process.stdout.write.bind(process.stdout);
if (captured) {
  const [rawConfig, workers] = captured;
  const graph = rawConfig._graph as Record<string, unknown> | undefined;
  const nodes = graph?.nodes as unknown[] | undefined;
  write(JSON.stringify({
    workers: workers.length,
    hasGraph: !!graph,
    workerNames: workers.map((w: any) => w.name),
    graphNodes: nodes?.length ?? 0,
  }) + '\n');
} else {
  write(JSON.stringify({ workers: 0, hasGraph: false, workerNames: [], error: 'no serialization' }) + '\n');
}
process.exit(0);
