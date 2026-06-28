import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  esbuild: {
    tsconfigRaw: {
      compilerOptions: {
        experimentalDecorators: true,
        emitDecoratorMetadata: true,
      },
    },
  },
  resolve: {
    alias: {
      '@conductoross/conductor-agent-sdk': path.resolve(__dirname, 'src/index.ts'),
    },
  },
  test: {
    globals: true,
    testTimeout: 60_000,
    // Run 3 test files concurrently. Credential names are unique per suite so
    // suites 1-5 don't conflict with each other. Suites 17/18 don't use
    // credentials. 3 forks cuts wall-clock roughly in half vs 2 forks while
    // keeping server load manageable on the shared SQLite-backed Conductor.
    pool: 'forks',
    poolOptions: {
      forks: {
        maxForks: 3,
        minForks: 1,
      },
    },
    include: ['tests/**/*.test.ts', '../../tests/e2e/*.test.ts'],
    reporters: ['verbose', 'junit'],
    outputFile: {
      junit: '../../e2e-results/junit-ts.xml',
    },
  },
});
