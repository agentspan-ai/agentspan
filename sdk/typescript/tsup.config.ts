import { defineConfig } from 'tsup';

export default defineConfig({
  entry: [
    'src/index.ts',
    'src/testing/index.ts',
    'src/validation/runner.ts',
    'src/wrappers/ai.ts',
    'src/wrappers/langgraph.ts',
    'src/wrappers/langchain.ts',
  ],
  format: ['esm', 'cjs'],
  dts: true,
  splitting: true,
  sourcemap: true,
  clean: true,
  target: 'node18',
});
