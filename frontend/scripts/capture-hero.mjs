/**
 * Capture retina-DPR README hero screenshot from a running demo, then
 * encode a WebP companion so README served from GitHub stays sharp on
 * 2×/3× displays without bloating the repo.
 *
 * Prerequisites (one-time per machine):
 *   npx playwright install chromium    # ~92 MB chromium-headless-shell
 *   # WebP encoding is optional — if `cwebp` (brew install webp) is not
 *   # on PATH, the script logs a hint and skips the WebP step.
 *
 * Usage:
 *   BASE_URL=https://dist-olcivbch.devinapps.com node scripts/capture-hero.mjs
 *
 * Defaults to localhost:5173. Writes into ../docs/:
 *   - hero-breakdown.png    (5-category bar chart frame, 3840 × 2700)
 *   - hero-breakdown.webp   (~3× smaller; consumed by README <picture>)
 *
 * Captures at deviceScaleFactor 3 so a 1280-wide viewport produces a
 * 3840-px-wide image.
 *
 * Override the captured domain with HERO_DOMAIN=example.com.
 * Skip the WebP step with SKIP_WEBP=1 (useful in CI where the binary
 * may not be installed).
 */
import { chromium } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DOCS_DIR = resolve(__dirname, '..', '..', 'docs');
const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173';
const DOMAIN = process.env.HERO_DOMAIN ?? 'stripe.com';
const SKIP_WEBP = process.env.SKIP_WEBP === '1';

async function main() {
  await mkdir(DOCS_DIR, { recursive: true });

  let browser;
  try {
    browser = await chromium.launch();
  } catch (err) {
    if (/Executable doesn't exist/i.test(String(err))) {
      console.error(
        'Chromium binary missing. Run: npx playwright install chromium',
      );
      process.exit(1);
    }
    throw err;
  }

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

  // Scroll so the five-category bars sit near the top of the viewport.
  // We anchor to a known heading so the crop is deterministic. Two
  // selectors so this keeps working before and after the h2-swap that
  // landed in PR #40 — pick whichever is present, fail loudly if
  // neither is (the page is broken, not the script).
  const newAnchor = page.getByRole('heading', { level: 2, name: /the breakdown/i });
  const legacyAnchor = page.getByText(/chapter — the breakdown/i).first();
  const newCount = await newAnchor.count();
  const legacyCount = newCount ? 0 : await legacyAnchor.count();
  if (!newCount && !legacyCount) {
    throw new Error(
      `Breakdown anchor not found on ${BASE_URL}/report/${DOMAIN} — ` +
        'neither the new h2 nor the legacy "chapter — the breakdown" ' +
        'text is present. Did the page render correctly?',
    );
  }
  const anchor = newCount ? newAnchor : legacyAnchor;
  await anchor.evaluate((el) => {
    const top = el.getBoundingClientRect().top + window.scrollY - 60;
    window.scrollTo({ top, behavior: 'instant' });
  });
  await page.waitForTimeout(400);

  const pngPath = resolve(DOCS_DIR, 'hero-breakdown.png');
  await page.screenshot({ path: pngPath, fullPage: false });
  console.log(`Wrote ${pngPath}`);

  await browser.close();

  // Encode the matching WebP. Optional — README falls back to PNG.
  if (!SKIP_WEBP) {
    encodeWebp(pngPath);
  }
}

function encodeWebp(pngPath) {
  const webpPath = pngPath.replace(/\.png$/, '.webp');
  const result = spawnSync('cwebp', ['-q', '85', '-quiet', pngPath, '-o', webpPath], {
    encoding: 'utf-8',
  });
  if (result.error && result.error.code === 'ENOENT') {
    console.warn(
      'cwebp not found on PATH — skipping WebP step. ' +
        'Install with `brew install webp` or set SKIP_WEBP=1 to silence this.',
    );
    return;
  }
  if (result.status !== 0) {
    console.warn(`cwebp exited ${result.status}: ${result.stderr}`);
    return;
  }
  console.log(`Wrote ${webpPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
