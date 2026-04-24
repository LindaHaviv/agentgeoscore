import { expect, test } from '@playwright/test';
import { BAND_REPORTS, reportWithErrors } from './fixtures/band-reports';

const SCAN_ENDPOINT = '**/api/scan';

// Verdict and kicker patterns must NOT overlap — C's verdict starts with
// "Middling" and its kicker is "grade · middling", which would collide under
// a single /middling/i regex and trigger a strict-mode multi-match. Same for
// F (Invisible).
const GRADE_VERDICTS: Record<string, RegExp> = {
  A: /will find and cite it/i,
  B: /tuning-up choices/i,
  C: /real gaps in how AI sees/i,
  D: /struggle to read or cite/i,
  F: /urgent fixes required/i,
};

const GRADE_WORDS: Record<string, RegExp> = {
  A: /grade · excellent/i,
  B: /grade · strong/i,
  C: /grade · middling/i,
  D: /grade · weak/i,
  F: /grade · invisible/i,
};

/**
 * Score-band coverage — renders every grade letter through the full
 * ScoreCard verdict/label mapping. Desktop-only (logic is viewport-agnostic).
 */
test.describe('score bands', () => {
  for (const [grade, report] of Object.entries(BAND_REPORTS)) {
    test(`grade ${grade} renders the matching score, verdict, and kicker`, async ({ page }) => {
      await page.route(SCAN_ENDPOINT, (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(report),
        }),
      );

      await page.goto(`/report/${report.domain}`);

      await expect(page.getByTestId('score-number')).toHaveText(String(report.score));
      await expect(page.getByTestId('score-grade')).toHaveText(grade);
      await expect(page.getByText(GRADE_VERDICTS[grade])).toBeVisible();
      await expect(page.getByText(GRADE_WORDS[grade])).toBeVisible();
    });
  }

  test('non-fatal scan errors surface as a warning footer on the report', async ({ page }) => {
    await page.route(SCAN_ENDPOINT, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(reportWithErrors),
      }),
    );

    await page.goto(`/report/${reportWithErrors.domain}`);
    await expect(page.getByTestId('score-number')).toHaveText(String(reportWithErrors.score));
    await expect(
      page.getByText(
        new RegExp(`Scan produced ${reportWithErrors.errors.length} non-fatal warning`, 'i'),
      ),
    ).toBeVisible();
  });
});
