/**
 * Pure helpers for the production-domain + freshness-date rewrites that the
 * Vite plugin in vite.config.ts applies at build time.
 *
 * Separated from vite.config.ts so they're independently unit-testable:
 * see src/test/origin-and-freshness.test.ts.
 */

/** The URL that source files reference verbatim. */
export const DEFAULT_ORIGIN = 'https://dist-olcivbch.devinapps.com';

/** Replace every occurrence of DEFAULT_ORIGIN with `targetOrigin`. */
export function rewriteOrigin(content: string, targetOrigin: string): string {
  // split/join avoids any regex-special-char surprises in the placeholder.
  return content.split(DEFAULT_ORIGIN).join(targetOrigin);
}

/**
 * Rewrite the byline freshness signal to a given date.
 *
 * Two patterns are recognised:
 *
 *   1. `<time datetime="YYYY-MM-DD">…</time>` — the machine-readable signal.
 *      Allows additional attributes (`class`, `aria-*`) before / after
 *      `datetime` so we don't break on future markup changes.
 *
 *   2. Visible-text "Updated <date>" inside a byline (anchored to a
 *      `byline`-class element). We don't rewrite arbitrary "Updated …"
 *      strings elsewhere — that's too eager and could match unrelated copy.
 *      (Plain-text public files like security.txt use `Expires:` and other
 *      RFC-9116 fields with different formats, so they're not touched.)
 */
export function rewriteUpdatedDate(
  content: string,
  isoDate: string,
  humanDate: string,
): string {
  let out = content;

  // <time datetime="YYYY-MM-DD" ...>VISIBLE</time>  →  today's date
  // Matches any extra attributes before/after `datetime`. Visible text gets
  // replaced with the human date.
  out = out.replace(
    /(<time\s+[^>]*?\bdatetime\s*=\s*")\d{4}-\d{2}-\d{2}("[^>]*>)[^<]+(<\/time>)/g,
    `$1${isoDate}$2${humanDate}$3`,
  );

  // Byline-class paragraph: "Updated YYYY-MM-DD" or "Updated Month D, YYYY".
  // Anchored to text inside a class="byline" element to avoid greedy
  // matches elsewhere in the page.
  out = out.replace(
    /(class="[^"]*\bbyline\b[^"]*"[^>]*>[^<]*?Updated\s+)(?:\d{4}-\d{2}-\d{2}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})/g,
    `$1${humanDate}`,
  );

  return out;
}

/** Build-style helper: rewrite both origin and date in one pass. */
export function rewriteAll(
  content: string,
  targetOrigin: string,
  isoDate: string,
  humanDate: string,
): string {
  return rewriteUpdatedDate(rewriteOrigin(content, targetOrigin), isoDate, humanDate);
}

/** Format today in en-US (locale-stable for CI). */
export function todayHuman(now: Date = new Date()): string {
  return now.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function todayIso(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}
