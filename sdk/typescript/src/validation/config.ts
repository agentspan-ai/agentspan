/**
 * Minimal TOML parser for validation config files.
 *
 * Supports:
 * - Key = value pairs (strings, numbers, booleans)
 * - [section] headers
 * - [[array_of_tables]] headers
 * - Comments (lines starting with #)
 * - Quoted strings (double and single quotes)
 */

export interface JudgeConfig {
  model: string;
  maxOutputChars?: number;
  maxTokens?: number;
  rateLimitSecs?: number;
}

export interface RunConfig {
  name: string;
  model: string;
  group?: string;
  timeout?: number;
  prompt?: string;
  rubrics?: string[];
}

export interface ValidationConfig {
  judge: JudgeConfig;
  runs: RunConfig[];
}

/**
 * Parse a value string into a typed JS value.
 */
function parseValue(raw: string): string | number | boolean | string[] {
  const trimmed = raw.trim();

  // Boolean
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;

  // Quoted string (double or single)
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }

  // Array of strings: ["a", "b"]
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    const inner = trimmed.slice(1, -1).trim();
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
  const num = Number(trimmed);
  if (!isNaN(num) && trimmed !== '') return num;

  // Fallback: unquoted string
  return trimmed;
}

/**
 * Parse a TOML config string into a ValidationConfig.
 */
export function parseToml(input: string): ValidationConfig {
  const config: ValidationConfig = {
    judge: { model: '' },
    runs: [],
  };

  let currentSection: string | null = null;
  let currentArrayItem: Record<string, unknown> | null = null;

  const lines = input.split('\n');

  for (const rawLine of lines) {
    const line = rawLine.trim();

    // Skip empty lines and comments
    if (line === '' || line.startsWith('#')) continue;

    // [[array_of_tables]]
    if (line.startsWith('[[') && line.endsWith(']]')) {
      // Flush any pending array item
      if (currentArrayItem && currentSection === 'runs') {
        config.runs.push(currentArrayItem as unknown as RunConfig);
      }
      currentSection = line.slice(2, -2).trim();
      if (currentSection === 'runs') {
        currentArrayItem = {};
      }
      continue;
    }

    // [section]
    if (line.startsWith('[') && line.endsWith(']')) {
      // Flush any pending array item
      if (currentArrayItem && currentSection === 'runs') {
        config.runs.push(currentArrayItem as unknown as RunConfig);
        currentArrayItem = null;
      }
      currentSection = line.slice(1, -1).trim();
      continue;
    }

    // key = value
    const eqIndex = line.indexOf('=');
    if (eqIndex === -1) continue;

    const key = line.slice(0, eqIndex).trim();
    const value = parseValue(line.slice(eqIndex + 1));

    if (currentSection === 'judge') {
      (config.judge as unknown as Record<string, unknown>)[
        camelCase(key)
      ] = value;
    } else if (currentSection === 'runs' && currentArrayItem) {
      currentArrayItem[camelCase(key)] = value;
    }
  }

  // Flush last array item
  if (currentArrayItem && currentSection === 'runs') {
    config.runs.push(currentArrayItem as unknown as RunConfig);
  }

  return config;
}

/**
 * Convert snake_case to camelCase.
 */
function camelCase(str: string): string {
  return str.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

/**
 * Load and parse a TOML config file.
 */
export function loadConfig(content: string): ValidationConfig {
  return parseToml(content);
}
