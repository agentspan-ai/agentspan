/**
 * Compare AgentConfig JSON from Python SDK and TypeScript SDK.
 *
 * Reads _configs directories from both SDKs and reports differences.
 *
 * Usage:
 *   cd sdk/typescript && npx tsx tests/compare-wire-format.ts
 */

import { readFileSync, readdirSync, existsSync } from 'fs';
import { join, dirname, basename } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const TS_DIR = join(__dirname, '_configs');
const PY_DIR = join(__dirname, '..', '..', 'python', 'examples', '_configs');

// ── Types ────────────────────────────────────────────────────────────

type DiffKind = 'MATCH' | 'MINOR_DIFF' | 'MISMATCH' | 'MISSING';

interface FieldDiff {
  path: string;
  kind: 'added' | 'removed' | 'changed' | 'type_changed';
  python?: unknown;
  typescript?: unknown;
}

interface CompareResult {
  example: string;
  status: DiffKind;
  diffs: FieldDiff[];
  notes: string[];
}

// ── Known SDK-level expected differences ─────────────────────────────

/**
 * Classify a diff as a "known SDK difference" (returns explanation string)
 * or null if it is a genuine mismatch.
 *
 * Known SDK differences are patterns that differ between the Python and
 * TypeScript SDKs by design, not by bug.
 */
function classifyKnownDiff(diff: FieldDiff): string | null {
  const p = diff.path;

  // 1. external: Python emits `external: false`, TS omits when false
  if (p.endsWith('.external') && diff.kind === 'removed' && diff.python === false) {
    return 'Python emits external:false explicitly; TS omits when false';
  }

  // 2. maxTurns / timeoutSeconds defaults
  if (p.endsWith('.maxTurns') && (diff.kind === 'removed' || diff.kind === 'added')) {
    const val = diff.python ?? diff.typescript;
    if (val === 25) {
      return 'Default maxTurns (25): Python emits, TS omits';
    }
  }
  if (p.endsWith('.timeoutSeconds') && (diff.kind === 'removed' || diff.kind === 'added')) {
    const val = diff.python ?? diff.typescript;
    if (val === 0) {
      return 'Default timeoutSeconds (0): Python emits, TS omits';
    }
  }

  // 3. outputSchema: Python auto-generates from return type hints, TS does not
  if (p.endsWith('.outputSchema') && diff.kind === 'removed' && diff.python != null) {
    return 'Python auto-generates outputSchema from return type; TS omits';
  }

  // 4. agent_tool naming: Python uses agent name, TS appends _tool
  if (p.match(/\.tools\[\d+\]\.name$/) && diff.kind === 'changed') {
    const py = String(diff.python ?? '');
    const ts = String(diff.typescript ?? '');
    if (ts === py + '_tool' || ts.endsWith('_tool')) {
      return `agent_tool naming: Python="${py}", TS="${ts}" (appends _tool)`;
    }
  }

  // 5. agent_tool description differs
  if (p.match(/\.tools\[\d+\]\.description$/) && diff.kind === 'changed') {
    const py = String(diff.python ?? '');
    const ts = String(diff.typescript ?? '');
    if (py.startsWith('Invoke the ') && ts.startsWith('Run ')) {
      return `agent_tool description: Python="${py}", TS="${ts}"`;
    }
  }

  // 6. agent_tool inputSchema: Python has {request: string}, TS has empty properties
  if (p.match(/\.tools\[\d+\]\.inputSchema/) && diff.kind === 'removed') {
    // Check if this is a request property or required array from agent_tool
    if (p.includes('.properties.request') || p.endsWith('.required')) {
      return 'agent_tool inputSchema: Python has request param; TS has empty properties';
    }
  }

  // 7. model on pipeline (pipe()): Python >> propagates model, TS pipe() does not
  if (p === '.model' && diff.kind === 'removed') {
    return 'Pipeline model: Python >> propagates self.model; TS pipe() omits';
  }

  // 8. Guardrail maxRetries default: Python emits maxRetries:3, TS omits for regex/llm guardrails
  if (p.endsWith('.maxRetries') && diff.kind === 'removed' && diff.python === 3) {
    return 'Guardrail maxRetries default (3): Python emits, TS omits';
  }

  // 9. Pydantic/Zod schema metadata differences in outputType
  if (p.includes('.outputType.schema')) {
    if (p.endsWith('.title') && diff.kind === 'removed') {
      return 'Pydantic adds title to schema; Zod does not';
    }
    if (p.endsWith('.$schema') && diff.kind === 'added') {
      return 'Zod adds $schema to outputType; Pydantic does not';
    }
    if (p.endsWith('.additionalProperties') && diff.kind === 'added') {
      return 'Zod adds additionalProperties:false; Pydantic does not';
    }
  }

  // 10. outputType.className: Pydantic uses class name, Zod uses "Output"
  if (p.endsWith('.outputType.className') && diff.kind === 'changed') {
    const ts = String(diff.typescript ?? '');
    if (ts === 'Output') {
      return `outputType className: Python uses Pydantic class name; TS defaults to "Output"`;
    }
  }

  // 11. Tool parameter naming: snake_case (Python) vs camelCase (Zod)
  if (p.match(/\.inputSchema\.properties\.\w+$/) && diff.kind === 'removed') {
    return null; // Let these through — they are genuine naming diffs in tool params
  }

  return null;
}

// ── Normalization ────────────────────────────────────────────────────

const IGNORE_FIELDS = new Set([
  'correlationId',
  'workflowId',
  'sessionId',
  'prompt',
  'media',
  'idempotencyKey',
]);

function normalize(val: unknown): unknown {
  if (val === null || val === undefined) return null;

  if (Array.isArray(val)) {
    return val.map((v) => normalize(v));
  }

  if (typeof val === 'object') {
    const obj = val as Record<string, unknown>;
    const result: Record<string, unknown> = {};
    const keys = Object.keys(obj).sort();

    for (const key of keys) {
      if (IGNORE_FIELDS.has(key)) continue;
      result[key] = normalize(obj[key]);
    }
    return result;
  }

  return val;
}

function normalizeSchema(schema: unknown): unknown {
  if (schema === null || schema === undefined) return null;
  if (typeof schema !== 'object') return schema;
  if (Array.isArray(schema)) {
    return schema.map((s) => normalizeSchema(s));
  }

  const obj = schema as Record<string, unknown>;
  const result: Record<string, unknown> = {};

  for (const [key, val] of Object.entries(obj)) {
    if (key === '$schema') continue;
    if (key === 'additionalProperties' && val === false) continue;

    if (key === 'properties' && typeof val === 'object' && val !== null) {
      const props = val as Record<string, unknown>;
      const normProps: Record<string, unknown> = {};
      for (const [pKey, pVal] of Object.entries(props)) {
        normProps[pKey] = normalizeSchema(pVal);
      }
      result[key] = normProps;
      continue;
    }

    result[key] = normalizeSchema(val);
  }

  return result;
}

function stripSchemaDescriptions(val: unknown): unknown {
  if (val === null || val === undefined) return null;
  if (typeof val !== 'object') return val;
  if (Array.isArray(val)) {
    return val.map((v) => stripSchemaDescriptions(v));
  }

  const obj = val as Record<string, unknown>;
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (key === 'description') continue;
    result[key] = stripSchemaDescriptions(value);
  }
  return result;
}

// ── Deep diff ────────────────────────────────────────────────────────

function deepDiff(
  py: unknown,
  ts: unknown,
  path: string,
  diffs: FieldDiff[],
): void {
  if (py == null && ts == null) return;

  if (py == null && ts != null) {
    diffs.push({ path, kind: 'added', typescript: ts });
    return;
  }
  if (py != null && ts == null) {
    diffs.push({ path, kind: 'removed', python: py });
    return;
  }

  if (typeof py !== typeof ts) {
    diffs.push({ path, kind: 'type_changed', python: py, typescript: ts });
    return;
  }

  if (Array.isArray(py) && Array.isArray(ts)) {
    const maxLen = Math.max(py.length, ts.length);
    for (let i = 0; i < maxLen; i++) {
      if (i >= py.length) {
        diffs.push({ path: `${path}[${i}]`, kind: 'added', typescript: ts[i] });
      } else if (i >= ts.length) {
        diffs.push({ path: `${path}[${i}]`, kind: 'removed', python: py[i] });
      } else {
        deepDiff(py[i], ts[i], `${path}[${i}]`, diffs);
      }
    }
    return;
  }

  if (typeof py === 'object' && typeof ts === 'object') {
    const pyObj = py as Record<string, unknown>;
    const tsObj = ts as Record<string, unknown>;
    const allKeys = new Set([...Object.keys(pyObj), ...Object.keys(tsObj)]);

    for (const key of allKeys) {
      const childPath = `${path}.${key}`;
      if (key in pyObj && !(key in tsObj)) {
        diffs.push({ path: childPath, kind: 'removed', python: pyObj[key] });
      } else if (!(key in pyObj) && key in tsObj) {
        diffs.push({ path: childPath, kind: 'added', typescript: tsObj[key] });
      } else {
        deepDiff(pyObj[key], tsObj[key], childPath, diffs);
      }
    }
    return;
  }

  if (py !== ts) {
    diffs.push({ path, kind: 'changed', python: py, typescript: ts });
  }
}

// ── Schema-aware comparison ──────────────────────────────────────────

function compareSchemaAware(
  py: unknown,
  ts: unknown,
  path: string,
  diffs: FieldDiff[],
  notes: string[],
): void {
  if (py == null && ts == null) return;
  if (typeof py !== 'object' || typeof ts !== 'object' || py == null || ts == null) {
    deepDiff(py, ts, path, diffs);
    return;
  }
  if (Array.isArray(py) || Array.isArray(ts)) {
    if (Array.isArray(py) && Array.isArray(ts)) {
      const maxLen = Math.max(py.length, ts.length);
      for (let i = 0; i < maxLen; i++) {
        if (i >= py.length) {
          diffs.push({ path: `${path}[${i}]`, kind: 'added', typescript: ts[i] });
        } else if (i >= ts.length) {
          diffs.push({ path: `${path}[${i}]`, kind: 'removed', python: py[i] });
        } else {
          compareSchemaAware(py[i], ts[i], `${path}[${i}]`, diffs, notes);
        }
      }
    } else {
      deepDiff(py, ts, path, diffs);
    }
    return;
  }

  const pyObj = py as Record<string, unknown>;
  const tsObj = ts as Record<string, unknown>;

  const allKeys = new Set([...Object.keys(pyObj), ...Object.keys(tsObj)]);
  for (const key of allKeys) {
    const childPath = `${path}.${key}`;

    if (key === 'inputSchema' || key === 'outputSchema' || key === 'schema') {
      const pySchema = stripSchemaDescriptions(normalizeSchema(pyObj[key]));
      const tsSchema = stripSchemaDescriptions(normalizeSchema(tsObj[key]));
      const schemaDiffs: FieldDiff[] = [];
      deepDiff(pySchema, tsSchema, childPath, schemaDiffs);
      if (schemaDiffs.length > 0) {
        notes.push(
          `${childPath}: Schema differences (Zod/Pydantic): ${schemaDiffs.length} diffs`,
        );
        for (const d of schemaDiffs) {
          const pyVal =
            d.python !== undefined ? ` py=${truncate(JSON.stringify(d.python), 50)}` : '';
          const tsVal =
            d.typescript !== undefined
              ? ` ts=${truncate(JSON.stringify(d.typescript), 50)}`
              : '';
          notes.push(`  ${d.kind} ${d.path}${pyVal}${tsVal}`);
        }
      }
    } else if (
      (key === 'tools' || key === 'agents' || key === 'conditions' ||
       key === 'guardrails' || key === 'handoffs' || key === 'callbacks') &&
      Array.isArray(pyObj[key]) && Array.isArray(tsObj[key])
    ) {
      const pyArr = pyObj[key] as unknown[];
      const tsArr = tsObj[key] as unknown[];
      const maxLen = Math.max(pyArr.length, tsArr.length);
      for (let i = 0; i < maxLen; i++) {
        if (i >= pyArr.length) {
          diffs.push({ path: `${childPath}[${i}]`, kind: 'added', typescript: tsArr[i] });
        } else if (i >= tsArr.length) {
          diffs.push({ path: `${childPath}[${i}]`, kind: 'removed', python: pyArr[i] });
        } else {
          compareSchemaAware(pyArr[i], tsArr[i], `${childPath}[${i}]`, diffs, notes);
        }
      }
    } else if (
      (key === 'config' || key === 'agentConfig' || key === 'termination' ||
       key === 'outputType' || key === 'router') &&
      typeof pyObj[key] === 'object' && typeof tsObj[key] === 'object'
    ) {
      compareSchemaAware(pyObj[key], tsObj[key], childPath, diffs, notes);
    } else {
      if (key in pyObj && !(key in tsObj)) {
        diffs.push({ path: childPath, kind: 'removed', python: pyObj[key] });
      } else if (!(key in pyObj) && key in tsObj) {
        diffs.push({ path: childPath, kind: 'added', typescript: tsObj[key] });
      } else {
        deepDiff(pyObj[key], tsObj[key], childPath, diffs);
      }
    }
  }
}

// ── Main comparison logic ────────────────────────────────────────────

function compareExample(exampleName: string): CompareResult {
  const pyPath = join(PY_DIR, `${exampleName}.json`);
  const tsPath = join(TS_DIR, `${exampleName}.json`);

  if (!existsSync(pyPath) || !existsSync(tsPath)) {
    const missing = [];
    if (!existsSync(pyPath)) missing.push('Python');
    if (!existsSync(tsPath)) missing.push('TypeScript');
    return {
      example: exampleName,
      status: 'MISSING',
      diffs: [],
      notes: [`Missing from: ${missing.join(', ')}`],
    };
  }

  const pyRaw = JSON.parse(readFileSync(pyPath, 'utf8'));
  const tsRaw = JSON.parse(readFileSync(tsPath, 'utf8'));

  const pyNorm = normalize(pyRaw);
  const tsNorm = normalize(tsRaw);

  const rawDiffs: FieldDiff[] = [];
  const notes: string[] = [];

  compareSchemaAware(pyNorm, tsNorm, '', rawDiffs, notes);

  // Classify diffs into known (-> notes) vs real mismatches (-> diffs)
  const realDiffs: FieldDiff[] = [];
  for (const d of rawDiffs) {
    const known = classifyKnownDiff(d);
    if (known) {
      notes.push(`${d.path}: ${known}`);
    } else {
      realDiffs.push(d);
    }
  }

  let status: DiffKind;
  if (realDiffs.length === 0 && notes.length === 0) {
    status = 'MATCH';
  } else if (realDiffs.length === 0) {
    status = 'MINOR_DIFF';
  } else {
    status = 'MISMATCH';
  }

  return { example: exampleName, status, diffs: realDiffs, notes };
}

// ── Collect all example names ────────────────────────────────────────

function getExampleNames(): string[] {
  const names = new Set<string>();

  if (existsSync(PY_DIR)) {
    for (const f of readdirSync(PY_DIR)) {
      if (f.endsWith('.json')) names.add(basename(f, '.json'));
    }
  }

  if (existsSync(TS_DIR)) {
    for (const f of readdirSync(TS_DIR)) {
      if (f.endsWith('.json')) names.add(basename(f, '.json'));
    }
  }

  return [...names].sort();
}

// ── Report ───────────────────────────────────────────────────────────

function printReport(results: CompareResult[]): void {
  const statusLabel: Record<DiffKind, string> = {
    MATCH: 'PASS',
    MINOR_DIFF: 'NOTE',
    MISMATCH: 'FAIL',
    MISSING: 'SKIP',
  };

  console.log('\n' + '='.repeat(90));
  console.log('  Wire Format Comparison: Python SDK vs TypeScript SDK');
  console.log('='.repeat(90));

  // Summary table
  console.log('\n  SUMMARY TABLE');
  console.log('  ' + '-'.repeat(86));
  console.log(
    `  ${'Example'.padEnd(44)} ${'Status'.padEnd(10)} ${'Real'.padEnd(6)} ${'Known'.padEnd(6)} Notes`,
  );
  console.log('  ' + '-'.repeat(86));

  for (const r of results) {
    console.log(
      `  ${r.example.padEnd(44)} ${(`[${statusLabel[r.status]}]`).padEnd(10)} ${String(r.diffs.length).padEnd(6)} ${String(r.notes.length).padEnd(6)} ${r.notes.length > 0 ? r.notes.length + ' known diffs' : ''}`,
    );
  }

  console.log('  ' + '-'.repeat(86));

  const matchCount = results.filter((r) => r.status === 'MATCH').length;
  const minorCount = results.filter((r) => r.status === 'MINOR_DIFF').length;
  const mismatchCount = results.filter((r) => r.status === 'MISMATCH').length;
  const missingCount = results.filter((r) => r.status === 'MISSING').length;

  console.log(
    `\n  Total: ${results.length}  |  PASS: ${matchCount}  |  MINOR (known diffs only): ${minorCount}  |  FAIL: ${mismatchCount}  |  SKIP: ${missingCount}`,
  );

  // Known difference categories summary
  console.log('\n  KNOWN DIFFERENCE CATEGORIES (not counted as failures):');
  console.log('    - external:false — Python emits, TS omits when false');
  console.log('    - maxTurns:25 / timeoutSeconds:0 — Python emits defaults, TS omits');
  console.log('    - outputSchema — Python generates from return type, TS omits');
  console.log('    - inputSchema descriptions — Zod .describe() vs Python docstrings');
  console.log('    - Schema metadata — $schema, additionalProperties, title');
  console.log('    - agent_tool naming — Python: agentName, TS: agentName_tool');
  console.log('    - agent_tool description wording — "Invoke" vs "Run"');
  console.log('    - agent_tool inputSchema — Python has request param, TS empty');
  console.log('    - outputType.className — Pydantic class name vs "Output"');
  console.log('    - Guardrail maxRetries default (3) — Python emits, TS omits');
  console.log('    - Pipeline model — Python >> propagates model, TS pipe() omits');

  // Detailed output for REAL mismatches
  const mismatches = results.filter((r) => r.status === 'MISMATCH');
  if (mismatches.length > 0) {
    console.log('\n' + '='.repeat(90));
    console.log('  REAL MISMATCHES (require investigation)');
    console.log('='.repeat(90));

    for (const r of mismatches) {
      console.log(`\n  --- ${r.example} [${statusLabel[r.status]}] ---`);

      if (r.diffs.length > 0) {
        console.log('  Structural differences:');
        for (const d of r.diffs) {
          const pyVal =
            d.python !== undefined ? ` py=${truncate(JSON.stringify(d.python), 60)}` : '';
          const tsVal =
            d.typescript !== undefined
              ? ` ts=${truncate(JSON.stringify(d.typescript), 60)}`
              : '';
          console.log(`    ${d.kind.toUpperCase()} ${d.path}${pyVal}${tsVal}`);
        }
      }
    }
  }

  // MINOR_DIFF details (optional)
  const minors = results.filter((r) => r.status === 'MINOR_DIFF');
  if (minors.length > 0) {
    console.log('\n' + '='.repeat(90));
    console.log('  MINOR DIFFERENCES (known SDK differences — informational)');
    console.log('='.repeat(90));

    for (const r of minors) {
      console.log(`\n  --- ${r.example} [${statusLabel[r.status]}] ---`);
      for (const n of r.notes) {
        console.log(`    ${n}`);
      }
    }
  }

  // MISSING
  const missing = results.filter((r) => r.status === 'MISSING');
  if (missing.length > 0) {
    console.log('\n  MISSING:');
    for (const r of missing) {
      console.log(`    ${r.example}: ${r.notes.join(', ')}`);
    }
  }

  console.log('\n' + '='.repeat(90));
}

function truncate(s: string, maxLen: number): string {
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen - 3) + '...';
}

// ── Main ─────────────────────────────────────────────────────────────

console.log(`Python configs: ${PY_DIR}`);
console.log(`TypeScript configs: ${TS_DIR}`);

if (!existsSync(PY_DIR)) {
  console.error(`\nERROR: Python config directory not found: ${PY_DIR}`);
  console.error('Run: cd sdk/python && uv run python examples/dump_agent_configs.py');
  process.exit(1);
}

if (!existsSync(TS_DIR)) {
  console.error(`\nERROR: TypeScript config directory not found: ${TS_DIR}`);
  console.error('Run: cd sdk/typescript && npx tsx tests/dump-agent-configs.ts');
  process.exit(1);
}

const exampleNames = getExampleNames();
if (exampleNames.length === 0) {
  console.error('\nERROR: No config files found in either directory.');
  process.exit(1);
}

const results = exampleNames.map(compareExample);
printReport(results);

// Exit with error code if any mismatches
const hasMismatch = results.some((r) => r.status === 'MISMATCH');
process.exit(hasMismatch ? 1 : 0);
