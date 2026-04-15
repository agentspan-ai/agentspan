import { readdirSync, statSync } from 'fs';
import { join, extname } from 'path';
import { Agent } from '../src/agent.js';
import { detectFramework } from '../src/frameworks/detect.js';

export interface DiscoveredAgent {
  obj: unknown;
  name: string;
  framework: string;
}

/** Directories that should never be scanned during discovery. */
const SKIP_DIRS = new Set([
  'node_modules', '.git', 'dist', 'build', '.next', '.venv', 'venv',
  '__pycache__', '.tox', '.eggs', 'coverage', '.nyc_output',
]);

/**
 * Recursively collect all .ts/.js file paths under a directory.
 * Skips common dependency / build / cache directories and symlinks.
 */
function collectFiles(dir: string): string[] {
  const results: string[] = [];
  const entries = readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name.startsWith('.') || SKIP_DIRS.has(entry.name)) continue;
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory() && !entry.isSymbolicLink()) {
      results.push(...collectFiles(fullPath));
    } else if (entry.isFile()) {
      const ext = extname(entry.name);
      if ((ext === '.ts' || ext === '.js') && !entry.name.startsWith('_') && !entry.name.endsWith('.d.ts')) {
        results.push(fullPath);
      }
    }
  }
  return results;
}

/**
 * Scan a directory recursively for .ts/.js files and discover all agent-like exports,
 * including native AgentSpan agents and framework agents (OpenAI, ADK,
 * LangChain, LangGraph).
 */
export async function discoverAllAgents(scanPath: string): Promise<DiscoveredAgent[]> {
  const filePaths = collectFiles(scanPath);
  const found: DiscoveredAgent[] = [];
  const seenNames = new Set<string>();

  for (const fullPath of filePaths) {
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
    } catch (e: any) {
      console.error(`Skipping ${fullPath}: ${e.message || e}`);
    }
  }

  return found;
}
