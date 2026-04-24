import { expect, test } from '@playwright/test';

/**
 * Header + footer chrome: external links open in new tabs with `noreferrer`
 * (XSS / tab-nabbing guard) and point at the canonical URLs we advertise.
 * Desktop-only — viewport-agnostic logic.
 */
test.describe('header and footer chrome', () => {
  test('header logo links to the homepage', async ({ page }) => {
    await page.goto('/report/stripe.com');
    const home = page.getByRole('link', { name: /home$/i });
    await expect(home).toHaveAttribute('href', '/');
  });

  test('"What\'s llms.txt?" header link opens llmstxt.org in a new tab', async ({ page }) => {
    await page.goto('/');
    const link = page.getByRole('link', { name: /llms\.txt\?/i });
    await expect(link).toHaveAttribute('href', 'https://llmstxt.org/');
    await expect(link).toHaveAttribute('target', '_blank');
    await expect(link).toHaveAttribute('rel', /noreferrer/);
  });

  test('GitHub header link opens the repo in a new tab', async ({ page }) => {
    await page.goto('/');
    const link = page.getByRole('link', { name: /^github$/i });
    await expect(link).toHaveAttribute('href', 'https://github.com/LindaHaviv/agentgeoscore');
    await expect(link).toHaveAttribute('target', '_blank');
    await expect(link).toHaveAttribute('rel', /noreferrer/);
  });
});
