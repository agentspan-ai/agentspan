import { describe, it, expect } from 'vitest';

describe('discover bin script', () => {
  it('should format discovered agents as JSON entries', async () => {
    const { formatDiscoveryResult } = await import('../../cli-bin/discover.js');
    const result = formatDiscoveryResult([
      { obj: {}, name: 'researcher', framework: 'native' },
      { obj: {}, name: 'summarizer', framework: 'openai' },
    ]);
    expect(result).toEqual([
      { name: 'researcher', framework: 'native' },
      { name: 'summarizer', framework: 'openai' },
    ]);
  });

  it('should return empty array when no agents found', async () => {
    const { formatDiscoveryResult } = await import('../../cli-bin/discover.js');
    const result = formatDiscoveryResult([]);
    expect(result).toEqual([]);
  });
});
