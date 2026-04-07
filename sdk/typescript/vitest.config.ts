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
    include: ['tests/**/*.test.ts', '../../tests/e2e/*.test.ts', 'examples/**/*.test.ts'],
  },
});
