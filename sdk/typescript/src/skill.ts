/**
 * Agent Skills integration — load agentskills.io skill directories as Agents.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import { execFileSync } from 'node:child_process';
import { Agent } from './agent.js';

// ── Error class ─────────────────────────────────────────────

/** Raised when a skill directory cannot be loaded. */
export class SkillLoadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SkillLoadError';
  }
}

// ── YAML frontmatter parsing ────────────────────────────────

/**
 * Minimal YAML parser for skill frontmatter.
 * Handles flat key-value pairs, nested objects (one level), and arrays.
 */
function parseYaml(text: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  const lines = text.split('\n');
  let currentKey: string | null = null;
  let currentObj: Record<string, unknown> | null = null;

  for (const line of lines) {
    // Skip blank lines and comments
    if (line.trim() === '' || line.trim().startsWith('#')) {
      if (currentKey && currentObj) {
        result[currentKey] = currentObj;
        currentKey = null;
        currentObj = null;
      }
      continue;
    }

    // Indented line → nested object property
    if (/^\s{2,}/.test(line) && currentKey) {
      if (!currentObj) currentObj = {};
      const trimmed = line.trim();
      const colonIdx = trimmed.indexOf(':');
      if (colonIdx > 0) {
        const k = trimmed.slice(0, colonIdx).trim();
        const v = trimmed.slice(colonIdx + 1).trim();
        currentObj[k] = parseYamlValue(v);
      }
      continue;
    }

    // Flush any pending nested object
    if (currentKey && currentObj) {
      result[currentKey] = currentObj;
      currentKey = null;
      currentObj = null;
    }

    // Top-level key: value
    const colonIdx = line.indexOf(':');
    if (colonIdx > 0) {
      const key = line.slice(0, colonIdx).trim();
      const rawValue = line.slice(colonIdx + 1).trim();
      if (rawValue === '' || rawValue === '{}') {
        // Could be a nested object on following lines or empty
        currentKey = key;
        currentObj = rawValue === '{}' ? {} : null;
        if (rawValue === '{}') {
          result[key] = {};
          currentKey = null;
          currentObj = null;
        }
      } else {
        result[key] = parseYamlValue(rawValue);
      }
    }
  }

  // Flush trailing nested object
  if (currentKey && currentObj) {
    result[currentKey] = currentObj;
  } else if (currentKey) {
    result[currentKey] = {};
  }

  return result;
}

/** Parse a YAML scalar value. */
function parseYamlValue(raw: string): unknown {
  if (raw === '' || raw === 'null' || raw === '~') return null;
  if (raw === 'true') return true;
  if (raw === 'false') return false;

  // Quoted string
  if ((raw.startsWith('"') && raw.endsWith('"')) || (raw.startsWith("'") && raw.endsWith("'"))) {
    return raw.slice(1, -1);
  }

  // Number
  const num = Number(raw);
  if (!isNaN(num) && raw !== '') return num;

  // Inline object: {key: value, ...}
  if (raw.startsWith('{') && raw.endsWith('}')) {
    const inner = raw.slice(1, -1).trim();
    if (inner === '') return {};
    const obj: Record<string, unknown> = {};
    // Simple comma-separated key: value pairs
    for (const pair of inner.split(',')) {
      const ci = pair.indexOf(':');
      if (ci > 0) {
        const k = pair.slice(0, ci).trim();
        const v = pair.slice(ci + 1).trim();
        obj[k] = parseYamlValue(v);
      }
    }
    return obj;
  }

  // Inline array: [a, b, ...]
  if (raw.startsWith('[') && raw.endsWith(']')) {
    const inner = raw.slice(1, -1).trim();
    if (inner === '') return [];
    return inner.split(',').map((s) => parseYamlValue(s.trim()));
  }

  return raw;
}

// ── Frontmatter parsing ─────────────────────────────────────

/** Extract YAML frontmatter from SKILL.md content. */
export function parseFrontmatter(content: string): Record<string, unknown> {
  const match = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
  if (!match) return {};
  const data = parseYaml(match[1]);
  if (!data.name || (typeof data.name === 'string' && data.name.trim() === '')) {
    throw new Error("SKILL.md missing required 'name' field in frontmatter");
  }
  return data;
}

/** Extract markdown body after frontmatter. */
export function extractBody(content: string): string {
  const match = content.match(/^---\s*\n[\s\S]*?\n---\s*\n([\s\S]*)/);
  if (!match) return content;
  return match[1].trim();
}

// ── Section splitting ───────────────────────────────────────

const SECTION_SPLIT_THRESHOLD = 50000; // characters (~15K tokens)

/** Slugify a heading: lowercase, spaces to hyphens, strip special chars. */
function slugify(text: string): string {
  let slug = text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
  slug = slug.replace(/^-+|-+$/g, '');
  return slug;
}

/** Split SKILL.md body into sections by ## headings. */
export function splitIntoSections(body: string): Record<string, string> {
  const sections: Record<string, string> = {};
  const parts = body.split(/(?=^## )/m);
  for (const part of parts) {
    const trimmed = part.trim();
    if (!trimmed.startsWith('## ')) continue;
    const firstLine = trimmed.split('\n', 1)[0];
    const headingText = firstLine.slice(3).trim();
    const slug = slugify(headingText);
    if (slug) {
      sections[slug] = trimmed;
    }
  }
  return sections;
}

// ── Language detection ───────────────────────────────────────

const EXTENSION_MAP: Record<string, string> = {
  '.py': 'python',
  '.sh': 'bash',
  '.js': 'node',
  '.mjs': 'node',
  '.ts': 'node',
  '.rb': 'ruby',
};

const SHEBANG_MAP: Record<string, string> = {
  python: 'python',
  python3: 'python',
  bash: 'bash',
  sh: 'bash',
  node: 'node',
  ruby: 'ruby',
};

/** Detect script language from file extension or shebang. */
function detectLanguage(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  if (ext in EXTENSION_MAP) return EXTENSION_MAP[ext];

  // Check shebang
  try {
    const firstLine = fs.readFileSync(filePath, 'utf-8').split('\n', 1)[0];
    if (firstLine.startsWith('#!')) {
      for (const [key, lang] of Object.entries(SHEBANG_MAP)) {
        if (firstLine.includes(key)) return lang;
      }
    }
  } catch {
    // ignore
  }
  return 'bash'; // default
}

// ── Parameter formatting ────────────────────────────────────

/**
 * Format skill parameters as a prompt prefix.
 * Returns `[Skill Parameters]\nkey: value\n...` or empty string.
 */
export function formatSkillParams(params: Record<string, unknown>): string {
  const keys = Object.keys(params);
  if (keys.length === 0) return '';
  const lines = keys.map((k) => `${k}: ${params[k]}`);
  return '[Skill Parameters]\n' + lines.join('\n');
}

/**
 * Prepend skill parameters to the user prompt.
 * Returns the original prompt when params is empty.
 */
export function formatPromptWithParams(prompt: string, params: Record<string, unknown>): string {
  const prefix = formatSkillParams(params);
  if (!prefix) return prompt;
  return `${prefix}\n\n[User Request]\n${prompt}`;
}

// ── Skill options ───────────────────────────────────────────

export interface SkillOptions {
  /** Model for the orchestrator agent. Also default for sub-agents. */
  model?: string;
  /** Per-sub-agent model overrides. */
  agentModels?: Record<string, string>;
  /** Additional directories to search for cross-skill references. */
  searchPath?: string[];
  /** Runtime parameter overrides, merged on top of SKILL.md frontmatter defaults. */
  params?: Record<string, unknown>;
}

export interface LoadSkillsOptions {
  /** Default model for all skills. */
  model?: string;
  /** Per-skill, per-sub-agent model overrides. */
  agentModels?: Record<string, Record<string, string>>;
}

// ── Cross-skill resolution ──────────────────────────────────

/** Resolve cross-skill references found in SKILL.md body. */
function resolveCrossSkills(
  skillMd: string,
  skillPath: string,
  searchPath?: string[],
): Record<string, unknown> {
  const body = extractBody(skillMd);

  // Match patterns: invoke/use/call <name> skill
  const pattern = /(?:invoke|use|call)\s+(?:the\s+)?([a-z][a-z0-9-]*)\s+skill/gi;
  const matches = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(body)) !== null) {
    matches.add(m[1].toLowerCase());
  }

  if (matches.size === 0) return {};

  // Build search path
  const dirs: string[] = [];
  const parentDir = path.dirname(skillPath);
  if (fs.existsSync(parentDir)) dirs.push(parentDir);
  dirs.push(path.resolve(process.cwd(), '.agents', 'skills'));
  dirs.push(path.join(os.homedir(), '.agents', 'skills'));
  if (searchPath) {
    dirs.push(...searchPath.map((p) => path.resolve(p.replace(/^~/, os.homedir()))));
  }

  const crossRefs: Record<string, unknown> = {};
  for (const refName of matches) {
    for (const d of dirs) {
      const refDir = path.join(d, refName);
      const refSkillMd = path.join(refDir, 'SKILL.md');
      if (fs.existsSync(refSkillMd) && path.resolve(refDir) !== skillPath) {
        const refMdContent = fs.readFileSync(refSkillMd, 'utf-8');
        const refAgentFiles: Record<string, string> = {};
        for (const f of listGlob(refDir, '*-agent.md')) {
          const aname = path.basename(f, '.md').replace(/-agent$/, '');
          refAgentFiles[aname] = fs.readFileSync(f, 'utf-8');
        }
        const refScripts: Record<string, Record<string, string>> = {};
        const refScriptsDir = path.join(refDir, 'scripts');
        if (fs.existsSync(refScriptsDir)) {
          for (const f of listFiles(refScriptsDir)) {
            const stem = path.basename(f, path.extname(f));
            refScripts[stem] = {
              filename: path.basename(f),
              language: detectLanguage(f),
            };
          }
        }
        const refResources: string[] = [];
        for (const subdir of ['references', 'examples', 'assets']) {
          const sd = path.join(refDir, subdir);
          if (fs.existsSync(sd)) {
            refResources.push(
              ...listFilesRecursive(sd).map((f) => path.relative(refDir, f)),
            );
          }
        }
        crossRefs[refName] = {
          skillMd: refMdContent,
          agentFiles: refAgentFiles,
          scripts: refScripts,
          resourceFiles: refResources.sort(),
        };
        break;
      }
    }
  }
  return crossRefs;
}

// ── File system helpers ─────────────────────────────────────

function expandPath(p: string): string {
  return path.resolve(p.replace(/^~/, os.homedir()));
}

/** List files matching a glob-like pattern in a directory (sorted). */
function listGlob(dir: string, pattern: string): string[] {
  if (!fs.existsSync(dir)) return [];
  const regex = new RegExp('^' + pattern.replace(/\*/g, '.*') + '$');
  return fs
    .readdirSync(dir)
    .filter((f) => regex.test(f))
    .sort()
    .map((f) => path.join(dir, f));
}

/** List files in a directory (sorted, non-recursive). */
function listFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => fs.statSync(path.join(dir, f)).isFile())
    .sort()
    .map((f) => path.join(dir, f));
}

/** List files recursively (sorted). */
function listFilesRecursive(dir: string): string[] {
  const results: string[] = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...listFilesRecursive(full));
    } else if (entry.isFile()) {
      results.push(full);
    }
  }
  return results.sort();
}

// ── Main skill() function ───────────────────────────────────

/**
 * Load an Agent Skills directory as an Agentspan Agent.
 *
 * @param skillPath - Path to skill directory containing SKILL.md.
 * @param options - Model, agent model overrides, search path, and runtime params.
 * @returns Agent that can be run, composed, deployed, and served.
 * @throws SkillLoadError if the directory is not a valid skill.
 */
export function skill(skillPath: string, options?: SkillOptions): Agent {
  const resolvedPath = expandPath(skillPath);
  const model = options?.model ?? '';
  const agentModels = options?.agentModels ?? {};
  const searchPath = options?.searchPath;
  const params = options?.params;

  // 1. Read SKILL.md (required)
  const skillMdPath = path.join(resolvedPath, 'SKILL.md');
  if (!fs.existsSync(skillMdPath)) {
    throw new SkillLoadError(
      `Directory ${resolvedPath} is not a valid skill: SKILL.md not found`,
    );
  }
  const skillMd = fs.readFileSync(skillMdPath, 'utf-8');
  const frontmatter = parseFrontmatter(skillMd);
  const name = frontmatter.name as string;

  // 1b. Extract default params from frontmatter and merge overrides
  const defaultParams: Record<string, unknown> = {};
  const fmParams = frontmatter.params;
  if (fmParams && typeof fmParams === 'object' && !Array.isArray(fmParams)) {
    for (const [pname, pdef] of Object.entries(fmParams as Record<string, unknown>)) {
      if (pdef && typeof pdef === 'object' && !Array.isArray(pdef) && 'default' in pdef) {
        defaultParams[pname] = (pdef as Record<string, unknown>).default;
      } else {
        defaultParams[pname] = pdef;
      }
    }
  }
  const mergedParams = { ...defaultParams, ...(params ?? {}) };

  // 2. Discover *-agent.md files
  const agentFiles: Record<string, string> = {};
  for (const f of listGlob(resolvedPath, '*-agent.md')) {
    const agentName = path.basename(f, '.md').replace(/-agent$/, '');
    agentFiles[agentName] = fs.readFileSync(f, 'utf-8');
  }

  // 3. Discover scripts
  const scripts: Record<string, Record<string, unknown>> = {};
  const scriptsDir = path.join(resolvedPath, 'scripts');
  if (fs.existsSync(scriptsDir)) {
    for (const f of listFiles(scriptsDir)) {
      const stem = path.basename(f, path.extname(f));
      scripts[stem] = {
        filename: path.basename(f),
        language: detectLanguage(f),
        path: f,
      };
    }
  }

  // 4. List resource files (paths only, not contents)
  const resourceFiles: string[] = [];
  for (const subdir of ['references', 'examples', 'assets']) {
    const d = path.join(resolvedPath, subdir);
    if (fs.existsSync(d)) {
      resourceFiles.push(
        ...listFilesRecursive(d)
          .map((f) => path.relative(resolvedPath, f))
          .sort(),
      );
    }
  }
  // Non-agent, non-SKILL.md files in root
  for (const f of listFiles(resolvedPath)) {
    const basename = path.basename(f);
    if (
      basename !== 'SKILL.md' &&
      !basename.endsWith('-agent.md') &&
      basename !== 'skill.yaml' &&
      basename !== 'skill.toml'
    ) {
      resourceFiles.push(basename);
    }
  }

  // 5. Resolve cross-skill references
  const crossRefs = resolveCrossSkills(skillMd, resolvedPath, searchPath);

  // 5b. Auto-split large SKILL.md bodies into sections
  const body = extractBody(skillMd);
  let skillSections: Record<string, string> = {};
  if (body.length > SECTION_SPLIT_THRESHOLD) {
    skillSections = splitIntoSections(body);
    if (Object.keys(skillSections).length > 0) {
      for (const sectionName of Object.keys(skillSections)) {
        resourceFiles.push(`skill_section:${sectionName}`);
      }
    }
  }

  // 6. Build raw config
  const rawConfig: Record<string, unknown> = {
    model: model ? String(model) : '',
    agentModels,
    skillMd,
    agentFiles,
    scripts: Object.fromEntries(
      Object.entries(scripts).map(([k, v]) => [
        k,
        { filename: v.filename, language: v.language },
      ]),
    ),
    resourceFiles,
    crossSkillRefs: crossRefs,
    defaultParams,
  };

  // 7. Return Agent with framework marker
  const agent = new Agent({ name, model: model || undefined });

  // Attach internal properties (not part of AgentOptions)
  const a = agent as unknown as Record<string, unknown>;
  a._framework = 'skill';
  a._framework_config = rawConfig;
  a._skill_path = resolvedPath;
  a._skill_scripts = scripts;
  a._skill_sections = skillSections;
  a._skill_params = mergedParams;

  return agent;
}

// ── loadSkills() ────────────────────────────────────────────

/**
 * Load all skills from a directory. Cross-references auto-resolved.
 *
 * @param dirPath - Directory containing skill subdirectories.
 * @param options - Default model and per-skill agent model overrides.
 * @returns Record mapping skill directory name to Agent.
 */
export function loadSkills(
  dirPath: string,
  options?: LoadSkillsOptions,
): Record<string, Agent> {
  const resolvedDir = expandPath(dirPath);
  const model = options?.model ?? '';
  const agentModelsMap = options?.agentModels ?? {};
  const skills: Record<string, Agent> = {};

  if (!fs.existsSync(resolvedDir)) return skills;

  for (const entry of fs.readdirSync(resolvedDir, { withFileTypes: true }).sort((a, b) =>
    a.name.localeCompare(b.name),
  )) {
    if (!entry.isDirectory()) continue;
    const skillDir = path.join(resolvedDir, entry.name);
    if (fs.existsSync(path.join(skillDir, 'SKILL.md'))) {
      const overrides = agentModelsMap[entry.name] ?? {};
      skills[entry.name] = skill(skillDir, { model, agentModels: overrides });
    }
  }
  return skills;
}

// ── Worker registration ─────────────────────────────────────

/** A worker function for a skill tool. */
export interface SkillWorker {
  name: string;
  description: string;
  func: (command?: string) => string;
}

const INTERPRETER_MAP: Record<string, string> = {
  python: 'python3',
  bash: 'bash',
  node: 'node',
  ruby: 'ruby',
};

/**
 * Create worker functions for a skill-based agent.
 * Returns SkillWorker instances for Conductor polling.
 */
export function createSkillWorkers(agent: Agent): SkillWorker[] {
  const a = agent as unknown as Record<string, unknown>;
  if (a._framework !== 'skill') return [];

  const workers: SkillWorker[] = [];
  const skillName = agent.name;
  const config = a._framework_config as Record<string, unknown>;
  const skillPath = a._skill_path as string;
  const scripts = (a._skill_scripts ?? {}) as Record<string, Record<string, unknown>>;

  // Script workers — one per script file
  for (const [toolName, scriptInfo] of Object.entries(scripts)) {
    const scriptFile = scriptInfo.path as string;
    const language = scriptInfo.language as string;
    const workerName = `${skillName}__${toolName}`;
    const interpreter = INTERPRETER_MAP[language] ?? 'bash';

    // Closure to capture interpreter and script path
    const func = ((interp: string, spath: string) => {
      return (command: string = ''): string => {
        try {
          const args = command ? splitArgs(command) : [];
          const result = execFileSync(interp, [spath, ...args], {
            encoding: 'utf-8',
            timeout: 300_000,
            maxBuffer: 10 * 1024 * 1024,
          });
          return result;
        } catch (err: unknown) {
          if (err && typeof err === 'object' && 'killed' in err && (err as Record<string, unknown>).killed) {
            return 'ERROR: Script execution timed out (300s)';
          }
          if (err && typeof err === 'object' && 'status' in err) {
            const e = err as { status: number; stderr?: string };
            return `ERROR (exit ${e.status}):\n${e.stderr ?? ''}`;
          }
          return `ERROR: ${err}`;
        }
      };
    })(interpreter, scriptFile);

    workers.push({
      name: workerName,
      description: `Run ${toolName} script from ${skillName} skill`,
      func,
    });
  }

  // read_skill_file worker
  const allowedFiles = new Set<string>(
    (config.resourceFiles as string[]) ?? [],
  );
  const skillSections = (a._skill_sections ?? {}) as Record<string, string>;

  if (allowedFiles.size > 0) {
    const readFunc = ((
      sdir: string,
      allowed: Set<string>,
      sections: Record<string, string>,
    ) => {
      return (filePath: string = ''): string => {
        if (!allowed.has(filePath)) {
          return `ERROR: '${filePath}' not found. Available: ${[...allowed].sort().join(', ')}`;
        }
        // Handle virtual skill_section:* paths
        if (filePath.startsWith('skill_section:')) {
          const sectionName = filePath.slice('skill_section:'.length);
          if (sectionName in sections) return sections[sectionName];
          return `ERROR: section '${sectionName}' not found`;
        }
        const target = path.resolve(sdir, filePath);
        // Safety check: ensure resolved path is within skill directory
        if (!target.startsWith(path.resolve(sdir))) {
          return `ERROR: '${filePath}' is outside the skill directory`;
        }
        try {
          return fs.readFileSync(target, 'utf-8');
        } catch (err) {
          return `ERROR reading '${filePath}': ${err}`;
        }
      };
    })(skillPath, allowedFiles, skillSections);

    workers.push({
      name: `${skillName}__read_skill_file`,
      description: `Read resource files from ${skillName} skill`,
      func: readFunc,
    });
  }

  return workers;
}

// ── Argument splitting ──────────────────────────────────────

/** Simple shell-like argument splitting (handles quotes). */
function splitArgs(command: string): string[] {
  const args: string[] = [];
  let current = '';
  let inSingle = false;
  let inDouble = false;

  for (let i = 0; i < command.length; i++) {
    const ch = command[i];
    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
    } else if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
    } else if (ch === ' ' && !inSingle && !inDouble) {
      if (current.length > 0) {
        args.push(current);
        current = '';
      }
    } else {
      current += ch;
    }
  }
  if (current.length > 0) args.push(current);
  return args;
}
