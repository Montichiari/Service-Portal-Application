import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config (T-DEBT-3). The suite runs against the **real stack** —
 * the Vite dev server and the FastAPI backend with its Postgres — never mocks
 * (frontend/CLAUDE.md, Testing). The auth behaviour worth testing is
 * inseparable from real `httpOnly` cookies, real CORS and real token rotation:
 * a mocked client cannot exercise a cookie JavaScript is forbidden to read.
 *
 * One command runs it: `npm run test:e2e`.
 */

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './src/e2e',
  // Serial on purpose. The tests share one real backend and one real database,
  // and at this size the wall-clock saving from parallelism is worth less than
  // a failure log you can read top to bottom.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [['list']],
  // A generous default: every test does real bcrypt work through register and
  // login, and the refresh-concurrency test deliberately holds a response.
  timeout: 30_000,
  expect: { timeout: 10_000 },
  globalSetup: './src/e2e/globalSetup.ts',
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Starts Vite only if it isn't already running, so this is equally usable
  // from a clean shell and alongside the dev server you already had open. The
  // backend is not started here — it is a separate service with its own
  // database; globalSetup checks it is up and says so plainly if it isn't.
  webServer: {
    command: 'npm run dev',
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
