/**
 * Bundle-size budget for the main JS chunk. Catches accidental dependency
 * bloat — adding a heavy library (moment, lodash, full react-icons import,
 * etc.) regresses gzip size by tens of KB before anyone notices in a Lighthouse
 * audit.
 *
 * Skips cleanly when `frontend/dist/` doesn't exist (CI runs the backend
 * pytest job in parallel with the frontend build, same pattern as
 * backend/tests/test_predict_self_score.py).
 *
 * Budget headroom is intentionally generous (~25% above current) so this test
 * doesn't fire on every minor PR. Tighten the budget once it starts feeling
 * loose.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { gzipSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';

const DIST_ASSETS = resolve(__dirname, '..', '..', 'dist', 'assets');

// Gzip budgets in KB. Current baseline (2026-05): main chunk ~65 KB gzip,
// CSS ~6 KB. Budgets allow ~25% headroom — adjust deliberately, not casually.
const MAIN_JS_GZIP_BUDGET_KB = 85;
const MAIN_CSS_GZIP_BUDGET_KB = 12;

function gzipSizeKb(filePath: string): number {
  const raw = readFileSync(filePath);
  return gzipSync(raw).byteLength / 1024;
}

function distExists(): boolean {
  try {
    return statSync(DIST_ASSETS).isDirectory();
  } catch {
    return false;
  }
}

// NOTE: `describe.skipIf` only skips the test bodies — the describe callback
// itself still runs at registration time. Keep the directory-listing call
// inside each `it()` body so vitest never touches dist/ when skipped (CI
// runs vitest BEFORE the build step, so dist/ doesn't exist there).
describe.skipIf(!distExists())('bundle-size budget', () => {
  it(`main JS chunk gzip stays under ${MAIN_JS_GZIP_BUDGET_KB} KB`, () => {
    const files = readdirSync(DIST_ASSETS);
    const mainJs = files.find((f) => /^index-.*\.js$/.test(f));
    expect(mainJs, 'no index-*.js in dist/assets — build broken?').toBeDefined();
    const sizeKb = gzipSizeKb(resolve(DIST_ASSETS, mainJs!));
    expect(
      sizeKb,
      `Main JS gzip is ${sizeKb.toFixed(2)} KB, budget is ${MAIN_JS_GZIP_BUDGET_KB} KB. ` +
        'If this regression is intentional, raise MAIN_JS_GZIP_BUDGET_KB in this test.',
    ).toBeLessThan(MAIN_JS_GZIP_BUDGET_KB);
  });

  it(`main CSS gzip stays under ${MAIN_CSS_GZIP_BUDGET_KB} KB`, () => {
    const files = readdirSync(DIST_ASSETS);
    const mainCss = files.find((f) => /^index-.*\.css$/.test(f));
    expect(mainCss, 'no index-*.css in dist/assets — build broken?').toBeDefined();
    const sizeKb = gzipSizeKb(resolve(DIST_ASSETS, mainCss!));
    expect(
      sizeKb,
      `Main CSS gzip is ${sizeKb.toFixed(2)} KB, budget is ${MAIN_CSS_GZIP_BUDGET_KB} KB. ` +
        'If this regression is intentional, raise MAIN_CSS_GZIP_BUDGET_KB in this test.',
    ).toBeLessThan(MAIN_CSS_GZIP_BUDGET_KB);
  });
});
