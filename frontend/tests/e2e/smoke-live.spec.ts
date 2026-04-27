import { expect, test } from '@playwright/test';

/**
 * End-to-end smoke test — *live* backend.
 *
 * Unlike smoke.spec.ts (which mocks /api/scan), this suite hits the real Fly
 * backend. Use it post-deploy to verify scoring, CORS, and the deployed SPA.
 *
 * Not part of the default `npm run test:e2e` — must be invoked explicitly:
 *
 *   npm run test:e2e:live
 *   # or, against the deployed preview bundle:
 *   BASE_URL=https://dist-fmlxigyj.devinapps.com npm run test:e2e:live
 *
 * The tests hard-code a score band for stripe.com (70-100, grade A or B). If
 * Stripe ever drops below that band, the test correctly fails and we investigate.
 */

const SCORE_TIMEOUT = 45_000;

test.describe('agentgeoscore smoke-live', () => {
  test('scanning stripe.com produces a real A-range score', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder('your-site.com').fill('stripe.com');
    await page.getByRole('button', { name: /score it/i }).click();

    await expect(page).toHaveURL(/\/report\/stripe\.com$/);

    const scoreEl = page.getByTestId('score-number');
    await expect(scoreEl).toBeVisible({ timeout: SCORE_TIMEOUT });

    const score = Number.parseInt((await scoreEl.textContent())?.trim() ?? '', 10);
    expect(Number.isFinite(score)).toBe(true);
    expect(score).toBeGreaterThanOrEqual(70);
    expect(score).toBeLessThanOrEqual(100);

    await expect(page.getByTestId('score-grade')).toHaveText(/^[AB]$/);
    await expect(page.getByText('skipped', { exact: false })).toBeVisible();
  });

  test('direct-loading /report/stripe.com returns 200 + re-runs the scan', async ({ page }) => {
    const response = await page.goto('/report/stripe.com');
    expect(response?.status()).toBe(200);

    const scoreEl = page.getByTestId('score-number');
    await expect(scoreEl).toBeVisible({ timeout: SCORE_TIMEOUT });

    const score = Number.parseInt((await scoreEl.textContent())?.trim() ?? '', 10);
    expect(score).toBeGreaterThanOrEqual(70);
  });
});
