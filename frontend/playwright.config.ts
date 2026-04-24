import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for agentscore frontend e2e smoke tests.
 *
 * - Local runs (no BASE_URL set): starts the Vite dev server and tests against http://localhost:5173.
 * - CI or preview runs: set BASE_URL=https://dist-fmlxigyj.devinapps.com to test the deployed build.
 *   When BASE_URL is set, the dev server is skipped.
 */
const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173';
const usingExternal = Boolean(process.env.BASE_URL);

// The "live" suite exercises the real Fly backend; exclude from the default run.
const LIVE_SPEC = '**/smoke-live.spec.ts';
const testIgnore = process.env.PLAYWRIGHT_LIVE ? [] : [LIVE_SPEC];

// Specs that are viewport-agnostic or pointless on mobile (keyboard, URL form
// edge cases, share buttons, navigation) only run on the desktop project.
// Per-project testIgnore fully overrides the top-level one, so each list must
// also re-exclude the live suite.
const NON_DESKTOP_IGNORE = [
  ...(process.env.PLAYWRIGHT_LIVE ? [] : [LIVE_SPEC]),
  '**/keyboard.spec.ts',
  '**/url-input.spec.ts',
  '**/share.spec.ts',
  '**/navigation.spec.ts',
  '**/smoke-bands.spec.ts',
  '**/chrome.spec.ts',
];

export default defineConfig({
  testDir: './tests/e2e',
  testIgnore,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    // Desktop: real 1280×720 Chromium viewport.
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 720 } },
    },
    // Tablet/mobile: emulate the viewport + user-agent but keep Chromium as
    // the engine. WebKit isn't pre-installed on CI runners and the point of
    // these projects is to exercise responsive Tailwind breakpoints, not
    // Safari-specific behaviour.
    {
      name: 'tablet',
      testIgnore: NON_DESKTOP_IGNORE,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 834, height: 1194 },
        deviceScaleFactor: 2,
        isMobile: false,
        hasTouch: true,
      },
    },
    {
      name: 'mobile',
      testIgnore: NON_DESKTOP_IGNORE,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 3,
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: usingExternal
    ? undefined
    : {
        command: 'npm run dev -- --port 5173 --strictPort',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
        env: {
          VITE_API_BASE:
            process.env.VITE_API_BASE ?? 'https://agentscore-backend-qocniunv.fly.dev',
        },
      },
});
