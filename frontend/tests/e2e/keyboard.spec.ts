import { expect, test } from '@playwright/test';
import { stripeReport } from './fixtures/stripe-report';

const SCAN_ENDPOINT = '**/api/scan';

/**
 * Keyboard-only navigation. Mobile devices have no physical keyboard so this
 * suite only runs on the desktop project (enforced via playwright.config.ts
 * testIgnore).
 */
test.describe('keyboard navigation', () => {
  test('Enter submits the form and navigates to the report page', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stripeReport),
      }),
    );
    await page.goto('/');

    const input = page.getByPlaceholder('your-site.com');
    // URLInput uses autoFocus, so the input should already be focused on load.
    await expect(input).toBeFocused();
    await input.fill('stripe.com');
    await input.press('Enter');

    await expect(page).toHaveURL(/\/report\/stripe\.com$/);
    await expect(page.getByTestId('score-number')).toHaveText('94');
  });

  test('Tab cycles through the primary interactive elements on the homepage', async ({ page }) => {
    await page.goto('/');

    // Input is auto-focused on mount.
    const input = page.getByPlaceholder('your-site.com');
    await expect(input).toBeFocused();

    // Fill the input so the submit button is enabled and therefore reachable
    // via Tab. A disabled button is not focusable and browsers skip it.
    await input.fill('stripe.com');

    // Tab forward: submit → example-site buttons in DOM order.
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: /score it/i })).toBeFocused();

    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'stripe.com' })).toBeFocused();

    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'shopify.com' })).toBeFocused();

    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'devin.ai' })).toBeFocused();
  });
});
