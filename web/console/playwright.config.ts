import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests of the console as a claims handler uses it: a real browser against the
 * console container and the core (`make console-up`, core running with claims analysed).
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env['CONSOLE_URL'] ?? 'http://localhost:4200',
    ...devices['Desktop Chrome'],
    trace: 'retain-on-failure',
  },
});
