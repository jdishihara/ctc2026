import { defineConfig } from 'vitest/config';

export default defineConfig({
  esbuild: { jsx: 'automatic', jsxImportSource: 'preact' },
  define: { __DEV__: 'true' },
  test: {
    // the integration suite drives real timers against the mock page; running files in parallel starved it under load
    fileParallelism: false,
    globals: true,
    include: ['tests/unit/**/*.test.ts', 'tests/integration/**/*.test.ts'],
    environment: 'node',
  },
});
