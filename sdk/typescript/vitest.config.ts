import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    testTimeout: 60_000,
    include: ['tests/**/*.test.ts', '../../tests/e2e/*.test.ts', 'examples/**/*.test.ts'],
  },
});
