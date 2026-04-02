import { describe, it, expect } from 'vitest';
import type { RunOptions } from '../../src/types.js';

describe('RunOptions context', () => {
  it('accepts context in RunOptions type', () => {
    const options: RunOptions = {
      context: { repo: 'test/repo', branch: 'main' },
    };
    expect(options.context).toEqual({ repo: 'test/repo', branch: 'main' });
  });

  it('is optional and defaults to undefined', () => {
    const options: RunOptions = {};
    expect(options.context).toBeUndefined();
  });
});
