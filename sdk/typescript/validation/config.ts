/**
 * Enhanced TOML configuration parser for the validation framework.
 *
 * Parses the runs.toml format with support for:
 * - [defaults] section with RunConfig fields
 * - [judge] section with JudgeConfig fields
 * - [runs.name] named run sections (merged with defaults)
 * - [[runs]] array-of-tables syntax
 * - Nested [runs.name.env] and [judge.env] sections
 * - Comments and quoted strings
 */

export interface RunConfig {
  name: string;
  model: string;
  group?: string;
  native?: boolean;
  parallel?: boolean;
  maxWorkers?: number;
  timeout?: number;
  serverUrl?: string;
  env?: Record<string, string>;
}

export interface JudgeConfig {
  model: string;
  maxOutputChars: number;
  maxTokens: number;
  rateLimitSecs: number;
  passThreshold: number;
  baselineRun?: string;
  env?: Record<string, string>;
}

export interface ValidationConfig {
  defaults: Partial<RunConfig>;
  judge: JudgeConfig;
  runs: RunConfig[];
  env?: Record<string, string>;
}

/**
 * Parse a value string into a typed JS value.
 */
function parseValue(raw: string): string | number | boolean | string[] {
  const trimmed = raw.trim();

  // Strip inline comment (but not inside quotes)
  let value = trimmed;
  if (!value.startsWith('"') && !value.startsWith("'") && !value.startsWith('[')) {
    const commentIdx = value.indexOf('#');
    if (commentIdx > 0) {
      value = value.slice(0, commentIdx).trim();
    }
  }

  // Boolean
  if (value === 'true') return true;
  if (value === 'false') return false;

  // Quoted string
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }

  // Array of strings
  if (value.startsWith('[') && value.endsWith(']')) {
    const inner = value.slice(1, -1).trim();
    if (inner === '') return [];
    return inner.split(',').map((s) => {
      const v = s.trim();
      if (
        (v.startsWith('"') && v.endsWith('"')) ||
        (v.startsWith("'") && v.endsWith("'"))
      ) {
        return v.slice(1, -1);
      }
      return v;
    });
  }

  // Number
  const num = Number(value);
  if (!isNaN(num) && value !== '') return num;

  // Fallback: unquoted string
  return value;
}

/**
 * Convert snake_case key to camelCase.
 */
function camelCase(str: string): string {
  return str.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

/**
 * Parse a TOML config string into a ValidationConfig.
 *
 * Supports two run formats:
 * 1. [runs.name] - named sections (Python-style)
 * 2. [[runs]] with name field - array-of-tables
 */
export function parseToml(input: string): ValidationConfig {
  const defaults: Record<string, unknown> = {};
  const judgeRaw: Record<string, unknown> = {};
  const judgeEnv: Record<string, string> = {};
  const globalEnv: Record<string, string> = {};
  const runs: Record<string, Record<string, unknown>> = {};
  const runEnvs: Record<string, Record<string, string>> = {};

  let currentSection: string | null = null;
  let currentRunName: string | null = null;
  let inArrayRun = false;
  let arrayRunItem: Record<string, unknown> | null = null;
  const arrayRuns: Record<string, unknown>[] = [];

  const lines = input.split('\n');

  for (const rawLine of lines) {
    const line = rawLine.trim();

    // Skip empty lines and comments
    if (line === '' || line.startsWith('#')) continue;

    // [[runs]] array-of-tables
    if (line === '[[runs]]') {
      // Flush pending array run
      if (arrayRunItem) {
        arrayRuns.push(arrayRunItem);
      }
      arrayRunItem = {};
      inArrayRun = true;
      currentSection = 'runs_array';
      currentRunName = null;
      continue;
    }

    // [section.subsection] headers
    if (line.startsWith('[') && line.endsWith(']') && !line.startsWith('[[')) {
      // Flush pending array run if we left the array section
      if (inArrayRun && arrayRunItem && !line.startsWith('[runs')) {
        arrayRuns.push(arrayRunItem);
        arrayRunItem = null;
        inArrayRun = false;
      }

      const sectionName = line.slice(1, -1).trim();

      if (sectionName === 'defaults') {
        currentSection = 'defaults';
        currentRunName = null;
      } else if (sectionName === 'judge') {
        currentSection = 'judge';
        currentRunName = null;
      } else if (sectionName === 'judge.env') {
        currentSection = 'judge.env';
        currentRunName = null;
      } else if (sectionName === 'env') {
        currentSection = 'env';
        currentRunName = null;
      } else if (sectionName === 'display') {
        currentSection = 'display';
        currentRunName = null;
      } else if (sectionName.startsWith('runs.') && sectionName.endsWith('.env')) {
        // [runs.name.env]
        const runName = sectionName.slice(5, -4);
        currentSection = 'run.env';
        currentRunName = runName;
        if (!runEnvs[runName]) runEnvs[runName] = {};
      } else if (sectionName.startsWith('runs.')) {
        // [runs.name]
        const runName = sectionName.slice(5);
        currentSection = 'runs';
        currentRunName = runName;
        if (!runs[runName]) runs[runName] = {};
      } else {
        currentSection = sectionName;
        currentRunName = null;
      }
      continue;
    }

    // Key = value
    const eqIndex = line.indexOf('=');
    if (eqIndex === -1) continue;

    const key = line.slice(0, eqIndex).trim();
    const value = parseValue(line.slice(eqIndex + 1));

    if (currentSection === 'defaults') {
      defaults[camelCase(key)] = value;
    } else if (currentSection === 'judge') {
      judgeRaw[camelCase(key)] = value;
    } else if (currentSection === 'judge.env') {
      judgeEnv[key] = String(value);
    } else if (currentSection === 'env') {
      globalEnv[key] = String(value);
    } else if (currentSection === 'runs' && currentRunName) {
      runs[currentRunName][camelCase(key)] = value;
    } else if (currentSection === 'run.env' && currentRunName) {
      runEnvs[currentRunName][key] = String(value);
    } else if (currentSection === 'runs_array' && arrayRunItem) {
      arrayRunItem[camelCase(key)] = value;
    }
  }

  // Flush last array run
  if (arrayRunItem) {
    arrayRuns.push(arrayRunItem);
  }

  // Build JudgeConfig
  const judge: JudgeConfig = {
    model: (judgeRaw.model as string) ?? 'gpt-4o-mini',
    maxOutputChars: (judgeRaw.maxOutputChars as number) ?? 3000,
    maxTokens: (judgeRaw.maxTokens as number) ?? 300,
    rateLimitSecs: (judgeRaw.rateLimitSecs as number) ?? (judgeRaw.rateLimit as number) ?? 0.5,
    passThreshold: (judgeRaw.passThreshold as number) ?? 3,
    baselineRun: judgeRaw.baselineRun as string | undefined,
    env: Object.keys(judgeEnv).length > 0 ? judgeEnv : undefined,
  };

  // Build RunConfigs from named sections
  const runConfigs: RunConfig[] = [];
  for (const [name, raw] of Object.entries(runs)) {
    const merged = { ...defaults, ...raw };
    runConfigs.push({
      name,
      model: (merged.model as string) ?? 'openai/gpt-4o-mini',
      group: merged.group as string | undefined,
      native: (merged.native as boolean) ?? false,
      parallel: (merged.parallel as boolean) ?? true,
      maxWorkers: (merged.maxWorkers as number) ?? 8,
      timeout: (merged.timeout as number) ?? 300,
      serverUrl: (merged.serverUrl as string) ?? 'http://localhost:8080/api',
      env: runEnvs[name] && Object.keys(runEnvs[name]).length > 0 ? runEnvs[name] : undefined,
    });
  }

  // Build RunConfigs from array-of-tables
  for (const raw of arrayRuns) {
    const merged = { ...defaults, ...raw };
    const name = (merged.name as string) ?? `run-${runConfigs.length}`;
    runConfigs.push({
      name,
      model: (merged.model as string) ?? 'openai/gpt-4o-mini',
      group: merged.group as string | undefined,
      native: (merged.native as boolean) ?? false,
      parallel: (merged.parallel as boolean) ?? true,
      maxWorkers: (merged.maxWorkers as number) ?? 8,
      timeout: (merged.timeout as number) ?? 300,
      serverUrl: (merged.serverUrl as string) ?? 'http://localhost:8080/api',
    });
  }

  return {
    defaults,
    judge,
    runs: runConfigs,
    env: Object.keys(globalEnv).length > 0 ? globalEnv : undefined,
  };
}

/**
 * Load and parse a TOML config from a file content string.
 */
export function loadConfig(content: string): ValidationConfig {
  return parseToml(content);
}
