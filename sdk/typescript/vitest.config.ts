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
      '@agentspan-ai/sdk': path.resolve(__dirname, 'src/index.ts'),
    },
  },
  test: {
    globals: true,
    testTimeout: 60_000,
    // Limit to 2 concurrent test files. GitHub Actions ubuntu-latest now uses
    // 4-core runners, causing vitest to default to 3 forks. Suites 17, 18, and 20
    // each fire 20–27 concurrent LLM-backed workflows; at 3 forks all three overlap,
    // saturating the shared Conductor server. Cap at 2 so at most two heavy suites
    // compete at once while keeping meaningful parallelism for the 15 min target.
    pool: 'forks',
    poolOptions: {
      forks: {
        maxForks: 2,
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
