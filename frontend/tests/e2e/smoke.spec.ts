import { expect, test, type Route } from '@playwright/test';
import { stripeReport } from './fixtures/stripe-report';

/**
 * End-to-end smoke test — mocked backend.
 *
 * The /api/scan response is intercepted via page.route() and replaced with a
 * fixture captured from the real backend. This keeps the suite fast (~1s per
 * test), deterministic, and runnable offline or without a working Fly deploy.
 *
 * A separate suite (smoke-live.spec.ts) exercises the real backend and is not
 * run in CI.
 */

const SCAN_ENDPOINT = '**/api/scan';

function mockScan(
  route: Route,
  body: unknown,
  init: { status?: number; delayMs?: number; contentType?: string } = {},
) {
  const { status = 200, delayMs = 0, contentType = 'application/json' } = init;
  const fulfill = () =>
    route.fulfill({
      status,
      contentType,
      body: typeof body === 'string' ? body : JSON.stringify(body),
    });
  if (delayMs > 0) return setTimeout(fulfill, delayMs);
  return fulfill();
}

test.describe('agentgeoscore smoke (mocked)', () => {
  test('homepage renders the Warm Editorial surface', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText(/a field guide · issue/i)).toBeVisible();
    await expect(
      page.getByRole('heading', { name: /Generative Engine.*Optimization.*graded/is }),
    ).toBeVisible();
    await expect(page.getByPlaceholder('your-site.com')).toBeVisible();
    await expect(page.getByRole('button', { name: /score it/i })).toBeVisible();
    await expect(page.getByRole('button', { name: 'stripe.com' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'devin.ai' })).toBeVisible();
  });

  test('scanning stripe.com renders the fixture score card', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) => mockScan(route, stripeReport));

    await page.goto('/');
    await page.getByRole('button', { name: 'stripe.com' }).click();

    await expect(page).toHaveURL(/\/report\/stripe\.com$/);

    await expect(page.getByTestId('score-number')).toHaveText(String(stripeReport.score));
    await expect(page.getByTestId('score-grade')).toHaveText(stripeReport.grade);
    await expect(page.getByText(/grade · excellent/i)).toBeVisible();

    // Regression check: skipped categories render as a "skipped" pill, not a 0/100 bar.
    await expect(page.getByText('skipped', { exact: false })).toBeVisible();
  });

  test('deep-link /report/:domain re-renders the scan from scratch', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) => mockScan(route, stripeReport));

    const response = await page.goto('/report/stripe.com');
    expect(response?.status(), 'SPA deep-link must return 200 (server fallback to index.html)').toBe(200);

    await expect(page.getByTestId('score-number')).toHaveText('94');
    await expect(page.getByTestId('score-grade')).toHaveText('A');
  });
});

test.describe('agentgeoscore smoke (error paths, mocked)', () => {
  test('backend returns 400 → error card shown, no score card', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) =>
      mockScan(route, { detail: 'invalid url: not-a-real-url' }, { status: 400 }),
    );

    await page.goto('/report/not-a-real-url');

    await expect(page.getByText(/unable to scan/i)).toBeVisible();
    await expect(page.getByText(/invalid url/i)).toBeVisible();
    await expect(page.getByTestId('score-number')).toHaveCount(0);
  });

  test('backend unreachable (network abort) → error message surfaced', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) => route.abort('failed'));

    await page.goto('/report/stripe.com');

    await expect(page.getByText(/unable to scan/i)).toBeVisible();
    await expect(page.getByTestId('score-number')).toHaveCount(0);
  });

  test('backend returns 500 + non-JSON body → error card shown', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) =>
      mockScan(route, '<html>server error</html>', {
        status: 500,
        contentType: 'text/html',
      }),
    );

    await page.goto('/report/stripe.com');

    await expect(page.getByText(/unable to scan/i)).toBeVisible();
    await expect(page.getByTestId('score-number')).toHaveCount(0);
  });

  test('scanning shows the loading indicator before the score card', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) => mockScan(route, stripeReport, { delayMs: 1500 }));

    await page.goto('/report/stripe.com');

    await expect(page.getByText(/Reading .*carefully/i)).toBeVisible();
    await expect(page.getByTestId('score-number')).toHaveText('94');
  });
});
