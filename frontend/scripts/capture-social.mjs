/**
 * Capture the GitHub social-preview image (1280 × 640).
 *
 * GitHub renders this for repo links shared to Twitter, Slack,
 * iMessage, LinkedIn, Discord, etc. The 1280×640 (2:1) frame is
 * cropped to ~1200×630 by most platforms — so the meaningful content
 * has to land in the centered 1.91:1 safe area.
 *
 * Output: docs/social-preview.png (~80–150 KB), uploaded manually via
 *   https://github.com/<owner>/<repo>/settings#repository-social-preview
 *   (the GitHub REST API does not expose this).
 *
 * Usage:
 *   BASE_URL=https://dist-olcivbch.devinapps.com node scripts/capture-social.mjs
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

  // Capture at 2× DPR so the 1280-wide social card renders sharp on
  // retina previews (Slack and iMessage both upsample).
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 640 },
    deviceScaleFactor: 2,
    colorScheme: 'light',
  });
  const page = await ctx.newPage();

  await page.goto(`${BASE_URL}/report/${DOMAIN}`, { waitUntil: 'domcontentloaded' });
  await page.getByTestId('score-number').waitFor({ state: 'visible', timeout: 60_000 });
  await page.waitForTimeout(800);

  // Capture the top 640 px — header + URL input + score card + start
  // of the breakdown. Forces the viewport-sized clip even if the page
  // extends below.
  const pngPath = resolve(DOCS_DIR, 'social-preview-2x.png');
  await page.screenshot({ path: pngPath, clip: { x: 0, y: 0, width: 1280, height: 640 } });

  await browser.close();
  console.log(`Wrote ${pngPath} (2560 × 1280 raw — downscale to 1280 × 640 for GitHub)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
