import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { stripeReport } from './fixtures/stripe-report';

const SCAN_ENDPOINT = '**/api/scan';

/**
 * Accessibility smoke — runs axe-core against the rendered DOM on every viewport.
 *
 * Scope: WCAG 2.1 Level AA. Color-contrast, keyboard focus, aria labels,
 * landmarks, heading order. Fails the test on any violation — if something
 * legitimately needs to be allowed, call `.disableRules([...])` explicitly so
 * the exception is visible in code review.
 */
function axeScanner(page: import('@playwright/test').Page) {
  return new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']);
}

test.describe('accessibility', () => {
  test('homepage has no WCAG AA violations', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /Generative Engine.*Optimization.*graded/is })).toBeVisible();
    const { violations } = await axeScanner(page).analyze();
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });

  test('report page has no WCAG AA violations', async ({ page }) => {
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
