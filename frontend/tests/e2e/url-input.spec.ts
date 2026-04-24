import { expect, test } from '@playwright/test';
import { stripeReport } from './fixtures/stripe-report';

const SCAN_ENDPOINT = '**/api/scan';

/**
 * End-to-end validation of the URL-input → normalization → routing path.
 *
 * `normalizeDomain` is unit-tested in vitest, but these tests prove the full
 * chain (user types, form submits, router navigates, report renders) works
 * for every shape a human might paste. Desktop-only — the logic is
 * viewport-agnostic so running on all three viewports would be pure overhead.
 */

const INPUTS: Array<{ raw: string; expectedPath: RegExp }> = [
  { raw: 'stripe.com', expectedPath: /\/report\/stripe\.com$/ },
  { raw: 'https://stripe.com', expectedPath: /\/report\/stripe\.com$/ },
  { raw: 'http://stripe.com', expectedPath: /\/report\/stripe\.com$/ },
  { raw: 'https://stripe.com/pricing', expectedPath: /\/report\/stripe\.com$/ },
  { raw: '  stripe.com  ', expectedPath: /\/report\/stripe\.com$/ },
  { raw: 'Stripe.com', expectedPath: /\/report\/stripe\.com$/ },
];

test.describe('URL input normalization (end-to-end)', () => {
  for (const { raw, expectedPath } of INPUTS) {
    test(`normalizes ${JSON.stringify(raw)} → /report/stripe.com`, async ({ page }) => {
      await page.route(SCAN_ENDPOINT, (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(stripeReport),
        }),
      );

      await page.goto('/');
      await page.getByPlaceholder('your-site.com').fill(raw);
      await page.getByRole('button', { name: /score it/i }).click();

      await expect(page).toHaveURL(expectedPath);
      await expect(page.getByTestId('score-number')).toHaveText('94');
    });
  }

  test('empty input does not submit', async ({ page }) => {
    await page.goto('/');
    // "Score It" button is disabled when value is empty.
    const submit = page.getByRole('button', { name: /score it/i });
    await expect(submit).toBeDisabled();

    await page.getByPlaceholder('your-site.com').fill('   ');
    // Whitespace-only still counts as empty after trim — submit stays usable
    // visually (has text) but the form's handler early-returns. Pressing
    // Enter should not navigate.
    await page.getByPlaceholder('your-site.com').press('Enter');
    await expect(page).toHaveURL(/\/$/);
  });
});
