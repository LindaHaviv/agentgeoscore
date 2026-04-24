import type { Report } from '../../../src/types';
import { stripeReport } from './stripe-report';

/**
 * Band fixtures — lightweight variants of the stripe fixture with score /
 * grade / domain swapped. Used by smoke-bands.spec.ts to assert the ScoreCard
 * renders the right verdict/colour band for every grade letter.
 */
function makeBandReport(
  domain: string,
  score: number,
  grade: Report['grade'],
  errors: string[] = [],
): Report {
  return {
    ...stripeReport,
    url: `https://${domain}/`,
    normalized_url: `https://${domain}/`,
    domain,
    score,
    grade,
    errors,
  };
}

export const BAND_REPORTS: Record<Report['grade'], Report> = {
  A: makeBandReport('band-a.test', 94, 'A'),
  B: makeBandReport('band-b.test', 76, 'B'),
  C: makeBandReport('band-c.test', 61, 'C'),
  D: makeBandReport('band-d.test', 45, 'D'),
  F: makeBandReport('band-f.test', 20, 'F'),
};

// A report with non-fatal errors for the warning-message test.
export const reportWithErrors: Report = makeBandReport('warnings.test', 82, 'B', [
  'citation_probe: gemini timed out after 15s',
  'discoverability: sitemap.xml returned 503',
]);
