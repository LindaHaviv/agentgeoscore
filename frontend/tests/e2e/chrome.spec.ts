import { expect, test } from '@playwright/test';

/**
 * Header + footer chrome: external links open in new tabs with `noreferrer`
 * (XSS / tab-nabbing guard) and point at the canonical URLs we advertise.
 * Desktop-only — viewport-agnostic logic.
 */
test.describe('header and footer chrome', () => {
  test('header logo links to the homepage', async ({ page }) => {
    await page.goto('/report/stripe.com');
    // Accessible name comes from the visible wordmark text now that we
    // dropped aria-label="AgentGEOScore home" (it was lying to screen
    // readers vs the visible "AgentGEOScore · issue №1" — Lighthouse's
    // label-content-name-mismatch audit caught it).
    const home = page.getByRole('link', { name: /Agent.*GEO.*Score/i }).first();
    await expect(home).toHaveAttribute('href', '/');
  });

  test('"The GEO paper" header link opens the arXiv paper in a new tab', async ({ page }) => {
    await page.goto('/');
    const link = page.getByRole('link', { name: /geo paper/i });
    await expect(link).toHaveAttribute('href', 'https://arxiv.org/abs/2311.09735');
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
