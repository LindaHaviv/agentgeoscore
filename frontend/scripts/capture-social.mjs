/**
 * Capture the GitHub social-preview image (1280 × 640, GitHub's
 * recommended size).
 *
 * GitHub renders this for repo links shared to Twitter, Slack,
 * iMessage, LinkedIn, Discord. Most platforms further crop it to
 * ~1.91:1, so the meaningful content has to land in the centered
 * safe area.
 *
 * The committed docs/social-preview.png is captured against the live
 * demo and is good to upload as-is — re-run this script only when the
 * report design changes or the demo moves to a new domain.
 *
 * Output: docs/social-preview.png (1280 × 640, single shot — no
 *   downscale step required). Upload manually via
 *   https://github.com/<owner>/<repo>/settings → "Social preview".
 *   The REST API does not expose social-preview uploads.
 *
 * Usage:
 *   node scripts/capture-social.mjs
 *     # captures against BASE_URL (default: http://localhost:5173)
 *     # against the HERO_DOMAIN report (default: stripe.com)
 *
 *   BASE_URL=https://dist-olcivbch.devinapps.com \
 *   HERO_DOMAIN=stripe.com \
 *   node scripts/capture-social.mjs
 */
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DOCS_DIR = resolve(__dirname, '..', '..', 'docs');
const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173';
const DOMAIN = process.env.HERO_DOMAIN ?? 'stripe.com';

async function main() {
  await mkdir(DOCS_DIR, { recursive: true });

  let browser;
  try {
    browser = await chromium.launch();
  } catch (err) {
    if (/Executable doesn't exist/i.test(String(err))) {
      console.error('Chromium binary missing. Run: npx playwright install chromium');
      process.exit(1);
    }
    throw err;
  }

  // Single try-finally so the browser is always closed even if the
  // capture itself throws (anchor missing, network error, etc.) —
  // otherwise the Chromium process leaks in CI.
  try {
    // Capture at native 1280 × 640 (DPR 1) so the output file IS the
    // final asset. Skipping the intermediate 2× downscale step
    // keeps the script single-step and matches GitHub's documented
    // upload size exactly — platforms further downsize for thumbnails.
    const ctx = await browser.newContext({
      viewport: { width: 1280, height: 640 },
      deviceScaleFactor: 1,
      colorScheme: 'light',
    });
    const page = await ctx.newPage();

    await page.goto(`${BASE_URL}/report/${DOMAIN}`, { waitUntil: 'domcontentloaded' });
    await page.getByTestId('score-number').waitFor({ state: 'visible', timeout: 60_000 });
    await page.waitForTimeout(800);

    const pngPath = resolve(DOCS_DIR, 'social-preview.png');
    await page.screenshot({
      path: pngPath,
      clip: { x: 0, y: 0, width: 1280, height: 640 },
    });
    console.log(`Wrote ${pngPath}`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
