import { expect, test } from '@playwright/test';
import { stripeReport } from './fixtures/stripe-report';

const SCAN_ENDPOINT = '**/api/scan';

/**
 * Navigation: browser-back restores the homepage, retry after a failed scan
 * works, and an invalid deep-link returns 200 via SPA fallback without
 * crashing. Desktop-only.
 */

test.describe('navigation', () => {
  test('browser back button returns to the homepage from a report', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stripeReport),
      }),
    );

    await page.goto('/');
    await page.getByRole('button', { name: 'stripe.com' }).click();
    await expect(page).toHaveURL(/\/report\/stripe\.com$/);
    await expect(page.getByTestId('score-number')).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { name: /Generative Engine.*Optimization.*graded/is })).toBeVisible();
  });

  test('retry after a failed scan: submitting a new URL renders a fresh report', async ({ page }) => {
    const calls: string[] = [];
    await page.route(SCAN_ENDPOINT, async (route) => {
      const body = route.request().postDataJSON() as { url: string };
      calls.push(body.url);
      if (body.url.includes('broken-domain.invalid')) {
        return route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'upstream failed' }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stripeReport),
      });
    });

    await page.goto('/report/broken-domain.invalid');
    await expect(page.getByText(/unable to scan/i)).toBeVisible();
    await expect(page.getByTestId('score-number')).toHaveCount(0);

    // Submit a new URL via the compact URLInput on the report page.
    await page.getByPlaceholder('your-site.com').fill('stripe.com');
    await page.getByRole('button', { name: /score it/i }).click();

    await expect(page).toHaveURL(/\/report\/stripe\.com$/);
    await expect(page.getByTestId('score-number')).toHaveText('94');
    await expect(page.getByText(/unable to scan/i)).toHaveCount(0);
    expect(calls.length).toBeGreaterThanOrEqual(2);
  });

  test('unknown deep-link renders the NotFound page with a Back-to-home link', async ({ page }) => {
    const response = await page.goto('/this-route-does-not-exist-12345');
    // SPA fallback: any unknown path serves index.html, then React Router's
    // wildcard route renders NotFoundPage. Asserting on the NotFound DOM
    // rather than just the 200 status guards against a misconfigured host
    // that would otherwise serve index.html for any path silently.
    expect(response?.status()).toBe(200);
    await expect(page.getByTestId('not-found')).toBeVisible();
    await expect(page.getByRole('heading', { name: /this page isn't in the field guide/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /back to the homepage/i })).toHaveAttribute('href', '/');
  });

  test('NotFound "Back to the homepage" link returns the user to /', async ({ page }) => {
    await page.goto('/still-not-a-real-route');
    await page.getByRole('link', { name: /back to the homepage/i }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { name: /Generative Engine.*Optimization.*graded/is })).toBeVisible();
  });
});
