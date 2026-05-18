import { readdirSync } from "fs";
import { join, extname } from "path";
import { Agent } from "./agent.js";

/**
 * Scan a directory for .ts/.js files, dynamically import them,
 * and return any exports that are Agent instances.
 */
export async function discoverAgents(path: string): Promise<Agent[]> {
  const agents: Agent[] = [];
  const entries = readdirSync(path, { withFileTypes: true });

  for (const entry of entries) {
    if (!entry.isFile()) continue;
    const ext = extname(entry.name);
    if (ext !== ".ts" && ext !== ".js") continue;

    const fullPath = join(path, entry.name);
    try {
      // Dynamic import — works with both ESM .js and .ts (via loader)
      const mod = await import(fullPath);
      for (const exportValue of Object.values(mod)) {
        if (exportValue instanceof Agent) {
          agents.push(exportValue);
        }
      }
    } catch {
      // Skip files that fail to import
    }
  }

  return agents;
}
