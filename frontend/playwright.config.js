import { defineConfig } from '@playwright/test';

// Serial end-to-end run against the simulator. The stack (embedded broker, simulator, app on 8765)
// is started per describe block by e2e/stack.js; global setup only checks prerequisites.
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.js',
  globalSetup: './e2e/global-setup.js',
  globalTeardown: './e2e/global-teardown.js',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  outputDir: '/tmp/pw-T19-results',
  use: {
    baseURL: 'http://localhost:8765',
    trace: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
