import { expect, test } from '@playwright/test';
import { stripeReport } from './fixtures/stripe-report';

const SCAN_ENDPOINT = '**/api/scan';

/**
 * ShareBar — "Copy link" writes the current URL to the clipboard and flips
 * the button label to "Copied ✓"; "Post on X" is an anchor pointing at
 * twitter.com/intent/tweet with the report score encoded. Desktop-only —
 * permission model for clipboard differs across mobile emulations.
 */

test.describe('share bar', () => {
  test.beforeEach(async ({ context, page }) => {
    // Chromium needs explicit permissions to read/write clipboard from page context.
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.route(SCAN_ENDPOINT, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stripeReport),
      }),
    );
  });

  test('"Copy link" writes the page URL and updates the button label', async ({ page }) => {
    await page.goto('/report/stripe.com');
    await expect(page.getByTestId('score-number')).toBeVisible();

    const copyButton = page.getByRole('button', { name: /^copy link$/i });
    await copyButton.click();

    await expect(page.getByRole('button', { name: /copied/i })).toBeVisible();

    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboardText).toMatch(/\/report\/stripe\.com$/);

    // Label resets after the 1.8s timeout in ShareBar.
    await expect(page.getByRole('button', { name: /^copy link$/i })).toBeVisible({ timeout: 4_000 });
  });

  test('"Post on X" links to twitter intent URL with encoded report summary', async ({ page }) => {
    await page.goto('/report/stripe.com');
    await expect(page.getByTestId('score-number')).toBeVisible();

    const postLink = page.getByRole('link', { name: /post on x/i });
    await expect(postLink).toHaveAttribute('target', '_blank');
    await expect(postLink).toHaveAttribute('rel', /noreferrer/);

    const href = await postLink.getAttribute('href');
    expect(href).toMatch(/^https:\/\/twitter\.com\/intent\/tweet\?text=/);
    const tweet = decodeURIComponent(href!.split('?text=')[1]);
    // Brand-agnostic assertions: structure + report details. The brand name
    // itself comes from src/brand.ts, so a rename won't break this test.
    expect(tweet).toContain('stripe.com');
    expect(tweet).toContain('94/100');
    expect(tweet).toContain('(A)');
    expect(tweet).toMatch(/scored 94\/100 \(A\) on \S+/);
    expect(tweet).toContain(page.url());
  });
});
