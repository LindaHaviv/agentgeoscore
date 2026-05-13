/**
 * Capture retina-DPR README hero screenshots from a running demo.
 *
 * Usage:
 *   BASE_URL=https://dist-olcivbch.devinapps.com node scripts/capture-hero.mjs
 *
 * Defaults to localhost:5173. Writes two PNGs into ../docs/:
 *   - hero-report.png       (full report page for stripe.com, light mode)
 *   - hero-breakdown.png    (cropped breakdown section)
 *
 * Captures at deviceScaleFactor 3 so a 1280-wide viewport produces a
 * 3840-px-wide image — sharp on 2× and 3× displays.
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

  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    deviceScaleFactor: 3,
    colorScheme: 'light',
  });
  const page = await ctx.newPage();

  // Go straight to the report page — it's a deep-linkable SPA route.
  await page.goto(`${BASE_URL}/report/${DOMAIN}`, { waitUntil: 'domcontentloaded' });

  // Wait for the live score to render.
  await page.getByTestId('score-number').waitFor({ state: 'visible', timeout: 60_000 });
  await page.waitForTimeout(800); // let the fade-in finish

  // Full-page hero — captures the score card + the start of the breakdown.
  await page.screenshot({
    path: resolve(DOCS_DIR, 'hero-report.png'),
    fullPage: false,
    omitBackground: false,
  });

  // Cropped breakdown — scroll the page so the five-category bars sit at
  // the top of the viewport. We prefer anchoring to a known heading so the
  // crop is deterministic, then nudge by ~80 px so the section kicker is
  // visible above the first bar.
  const newAnchor = page.getByRole('heading', { level: 2, name: /the breakdown/i });
  const legacyAnchor = page.getByText(/chapter — the breakdown/i).first();
  const anchor = (await newAnchor.count()) ? newAnchor : legacyAnchor;
  await anchor.evaluate((el) => {
    const top = el.getBoundingClientRect().top + window.scrollY - 60;
    window.scrollTo({ top, behavior: 'instant' });
  });
  await page.waitForTimeout(400);
  await page.screenshot({
    path: resolve(DOCS_DIR, 'hero-breakdown.png'),
    fullPage: false,
  });

  await browser.close();
  console.log(`Wrote ${DOCS_DIR}/hero-report.png and hero-breakdown.png`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
