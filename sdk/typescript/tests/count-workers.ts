/**
 * Count workers for all LangGraph examples by running each in a subprocess.
 * Usage: npx tsx tests/count-workers.ts
 */
import { readdirSync } from 'fs';
import { join } from 'path';
import { execSync } from 'child_process';

const sdkRoot = join(import.meta.dirname!, '..');
const examplesDir = join(sdkRoot, 'examples', 'langgraph');
const harness = join(sdkRoot, 'tests', '_worker-harness.ts');

const files = readdirSync(examplesDir)
  .filter(f => f.match(/^\d+.*\.ts$/) && !f.includes('README'))
  .sort();

interface Result {
  example: string;
  workers: number;
  hasGraph: boolean;
  workerNames?: string[];
  error?: string;
}

const results: Result[] = [];

for (const file of files) {
  const num = file.match(/^(\d+)/)?.[1] ?? '';
  const filePath = join(examplesDir, file);

  try {
    const output = execSync(
      `npx tsx "${harness}" "${filePath}"`,
      { cwd: sdkRoot, timeout: 15000, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
    ).trim();

    const lines = output.split('\n').filter(l => l.trim());
    const jsonLine = lines[lines.length - 1];
    const data = JSON.parse(jsonLine);
    results.push({ example: num, ...data });
  } catch (e: any) {
    const stdout = e.stdout?.toString()?.trim() ?? '';
    const lines = stdout.split('\n').filter((l: string) => l.trim());
    try {
      const jsonLine = lines[lines.length - 1];
      const data = JSON.parse(jsonLine);
      results.push({ example: num, ...data });
    } catch {
      const stderr = (e.stderr?.toString() ?? '').slice(0, 100);
      results.push({ example: num, workers: -1, hasGraph: false, error: stderr || e.message?.slice(0, 60) });
    }
  }
}

console.log(JSON.stringify(results, null, 2));
