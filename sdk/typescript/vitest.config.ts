import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    testTimeout: 60_000,
    include: ['tests/**/*.test.ts'],
    exclude: ['**/node_modules/**', '**/e2e/**'],
  },
});
