import { describe, it, expect } from 'vitest';
import * as path from 'node:path';
import {
  skill,
  loadSkills,
  SkillLoadError,
  formatSkillParams,
  formatPromptWithParams,
  createSkillWorkers,
  parseFrontmatter,
  extractBody,
  splitIntoSections,
} from '../../src/skill.js';
import { Agent } from '../../src/agent.js';
import { detectFramework } from '../../src/frameworks/detect.js';

const FIXTURES = path.resolve(__dirname, '../fixtures/skills');
const TEST_SKILL_PATH = path.join(FIXTURES, 'test-skill');

// ── parseFrontmatter ─────────────────────────────────────────

describe('parseFrontmatter', () => {
  it('extracts name and params from SKILL.md', () => {
    const content = `---
name: my-skill
description: A test skill
params:
  rounds: 3
  style: verbose
---

# My Skill`;
    const fm = parseFrontmatter(content);
    expect(fm.name).toBe('my-skill');
    expect(fm.description).toBe('A test skill');
    expect(fm.params).toEqual({ rounds: 3, style: 'verbose' });
  });

  it('returns empty object when no frontmatter', () => {
    expect(parseFrontmatter('# Just a heading')).toEqual({});
  });

  it('throws when name is missing', () => {
    const content = `---
description: No name
---

Body`;
    expect(() => parseFrontmatter(content)).toThrow("missing required 'name'");
  });
});

// ── extractBody ──────────────────────────────────────────────

describe('extractBody', () => {
  it('extracts body after frontmatter', () => {
    const content = `---
name: test
---

# Body Here`;
    expect(extractBody(content)).toBe('# Body Here');
  });

  it('returns full content when no frontmatter', () => {
    expect(extractBody('# No frontmatter')).toBe('# No frontmatter');
  });
});

// ── splitIntoSections ────────────────────────────────────────

describe('splitIntoSections', () => {
  it('splits body into sections by ## headings', () => {
    const body = `## Instructions

Do the thing.

## Examples

Here are examples.`;
    const sections = splitIntoSections(body);
    expect(Object.keys(sections)).toEqual(['instructions', 'examples']);
    expect(sections['instructions']).toContain('Do the thing');
    expect(sections['examples']).toContain('Here are examples');
  });

  it('skips content before first heading', () => {
    const body = `Preamble text

## Real Section

Content`;
    const sections = splitIntoSections(body);
    expect(Object.keys(sections)).toEqual(['real-section']);
  });

  it('returns empty for no headings', () => {
    expect(splitIntoSections('Just plain text')).toEqual({});
  });
});

// ── formatSkillParams ────────────────────────────────────────

describe('formatSkillParams', () => {
  it('formats params as [Skill Parameters] block', () => {
    const result = formatSkillParams({ rounds: 3, style: 'verbose' });
    expect(result).toBe('[Skill Parameters]\nrounds: 3\nstyle: verbose');
  });

  it('returns empty string for empty params', () => {
    expect(formatSkillParams({})).toBe('');
  });
});

// ── formatPromptWithParams ───────────────────────────────────

describe('formatPromptWithParams', () => {
  it('prepends params to prompt', () => {
    const result = formatPromptWithParams('Review this code', { rounds: 3 });
    expect(result).toContain('[Skill Parameters]');
    expect(result).toContain('rounds: 3');
    expect(result).toContain('[User Request]');
    expect(result).toContain('Review this code');
  });

  it('returns original prompt for empty params', () => {
    expect(formatPromptWithParams('Hello', {})).toBe('Hello');
  });
});

// ── skill() ──────────────────────────────────────────────────

describe('skill', () => {
  it('loads a skill directory as an Agent', () => {
    const agent = skill(TEST_SKILL_PATH, { model: 'openai/gpt-4o' });
    expect(agent).toBeInstanceOf(Agent);
    expect(agent.name).toBe('test-skill');
    expect(agent.model).toBe('openai/gpt-4o');
  });

  it('sets _framework to skill', () => {
    const agent = skill(TEST_SKILL_PATH);
    const a = agent as unknown as Record<string, unknown>;
    expect(a._framework).toBe('skill');
  });

  it('sets _framework_config with expected keys', () => {
    const agent = skill(TEST_SKILL_PATH, { model: 'openai/gpt-4o' });
    const a = agent as unknown as Record<string, unknown>;
    const config = a._framework_config as Record<string, unknown>;
    expect(config.model).toBe('openai/gpt-4o');
    expect(config.skillMd).toContain('test-skill');
    expect(config.agentFiles).toHaveProperty('reviewer');
    expect(config.scripts).toHaveProperty('lint');
    expect(config.scripts).toHaveProperty('analyze');
    expect(Array.isArray(config.resourceFiles)).toBe(true);
  });

  it('discovers agent files', () => {
    const agent = skill(TEST_SKILL_PATH);
    const a = agent as unknown as Record<string, unknown>;
    const config = a._framework_config as Record<string, unknown>;
    const agentFiles = config.agentFiles as Record<string, string>;
    expect(agentFiles).toHaveProperty('reviewer');
    expect(agentFiles['reviewer']).toContain('Reviewer Agent');
  });

  it('discovers scripts with language detection', () => {
    const agent = skill(TEST_SKILL_PATH);
    const a = agent as unknown as Record<string, unknown>;
    const config = a._framework_config as Record<string, unknown>;
    const scripts = config.scripts as Record<string, Record<string, string>>;
    expect(scripts.lint.language).toBe('bash');
    expect(scripts.analyze.language).toBe('python');
  });

  it('discovers resource files', () => {
    const agent = skill(TEST_SKILL_PATH);
    const a = agent as unknown as Record<string, unknown>;
    const config = a._framework_config as Record<string, unknown>;
    const resourceFiles = config.resourceFiles as string[];
    expect(resourceFiles.some((f) => f.includes('guide.md'))).toBe(true);
  });

  it('merges default and runtime params', () => {
    const agent = skill(TEST_SKILL_PATH, { params: { rounds: 5, extra: true } });
    const a = agent as unknown as Record<string, unknown>;
    const params = a._skill_params as Record<string, unknown>;
    expect(params.rounds).toBe(5); // overridden
    expect(params.style).toBe('verbose'); // default kept
    expect(params.extra).toBe(true); // new
  });

  it('throws SkillLoadError for missing SKILL.md', () => {
    expect(() => skill('/nonexistent/path')).toThrow(SkillLoadError);
  });

  it('throws SkillLoadError for directory without SKILL.md', () => {
    expect(() => skill(FIXTURES)).toThrow(SkillLoadError);
  });
});

// ── loadSkills() ─────────────────────────────────────────────

describe('loadSkills', () => {
  it('loads all skills from a directory', () => {
    const skills = loadSkills(FIXTURES, { model: 'openai/gpt-4o' });
    expect(Object.keys(skills).sort()).toEqual(['other-skill', 'test-skill']);
    expect(skills['test-skill']).toBeInstanceOf(Agent);
    expect(skills['other-skill']).toBeInstanceOf(Agent);
  });

  it('returns empty for nonexistent directory', () => {
    expect(loadSkills('/nonexistent/dir')).toEqual({});
  });
});

// ── createSkillWorkers() ─────────────────────────────────────

describe('createSkillWorkers', () => {
  it('creates workers for script-based skills', () => {
    const agent = skill(TEST_SKILL_PATH);
    const workers = createSkillWorkers(agent);

    // Should have script workers + read_skill_file worker
    const names = workers.map((w) => w.name);
    expect(names).toContain('test-skill__lint');
    expect(names).toContain('test-skill__analyze');
    expect(names).toContain('test-skill__read_skill_file');
  });

  it('returns empty for non-skill agents', () => {
    const agent = new Agent({ name: 'regular' });
    expect(createSkillWorkers(agent)).toEqual([]);
  });

  it('read_skill_file worker reads allowed files', () => {
    const agent = skill(TEST_SKILL_PATH);
    const workers = createSkillWorkers(agent);
    const readWorker = workers.find((w) => w.name.endsWith('__read_skill_file'));
    expect(readWorker).toBeDefined();

    const result = readWorker!.func('references/guide.md');
    expect(result).toContain('Guide');
  });

  it('read_skill_file worker rejects disallowed files', () => {
    const agent = skill(TEST_SKILL_PATH);
    const workers = createSkillWorkers(agent);
    const readWorker = workers.find((w) => w.name.endsWith('__read_skill_file'));
    const result = readWorker!.func('../../etc/passwd');
    expect(result).toContain('ERROR');
  });
});

// ── detectFramework integration ──────────────────────────────

describe('detectFramework', () => {
  it('detects skill agents as skill framework', () => {
    const agent = skill(TEST_SKILL_PATH);
    expect(detectFramework(agent)).toBe('skill');
  });

  it('returns null for regular agents', () => {
    const agent = new Agent({ name: 'regular' });
    expect(detectFramework(agent)).toBeNull();
  });
});
