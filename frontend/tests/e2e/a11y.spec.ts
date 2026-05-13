import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { stripeReport } from './fixtures/stripe-report';

const SCAN_ENDPOINT = '**/api/scan';

/**
 * Accessibility smoke — runs axe-core against the rendered DOM on every
 * Playwright project (desktop / tablet / mobile via playwright.config.ts).
 *
 * Scope: WCAG 2.1 + 2.2 Level AA plus axe-core's `best-practice` tag.
 *
 * Why `best-practice`: WCAG-AA alone misses checks like
 * `label-content-name-mismatch` (visible text doesn't match accessible name)
 * — that one only surfaced via Lighthouse last cycle. Including
 * `best-practice` here catches the same class of bug at PR time on every
 * viewport, instead of relying on Lighthouse's mobile-emulated pass alone.
 *
 * Fails the test on any violation. If something legitimately needs to be
 * allowed, call `.disableRules([...])` explicitly so the exception is
 * visible in code review.
 */
function axeScanner(page: import('@playwright/test').Page) {
  return new AxeBuilder({ page }).withTags([
    'wcag2a',
    'wcag2aa',
    'wcag21a',
    'wcag21aa',
    'wcag22aa',
    'best-practice',
  ]);
}

test.describe('accessibility', () => {
  test('homepage has no axe violations', async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Generative Engine.*Optimization.*graded/is }),
    ).toBeVisible();
    const { violations } = await axeScanner(page).analyze();
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });

  test('report page has no axe violations', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stripeReport),
      }),
    );
    await page.goto('/report/stripe.com');
    await expect(page.getByTestId('score-number')).toBeVisible();
    const { violations } = await axeScanner(page).analyze();
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });
});
