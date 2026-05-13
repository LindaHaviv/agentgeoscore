/**
 * Unit tests for the build-time rewriter helpers used by vite.config.ts's
 * origin-and-freshness Vite plugin.
 */
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_API_BASE,
  DEFAULT_ORIGIN,
  rewriteAll,
  rewriteApiBase,
  rewriteCopyrightYear,
  rewriteOrigin,
  rewriteUpdatedDate,
  todayHuman,
  todayIso,
} from '../../vite-plugins/origin-and-freshness';

describe('rewriteOrigin', () => {
  it('replaces every occurrence of the default origin', () => {
    const input = `<a href="${DEFAULT_ORIGIN}/x">x</a><a href="${DEFAULT_ORIGIN}/y">y</a>`;
    const out = rewriteOrigin(input, 'https://preview-abc.pages.dev');
    expect(out).toBe(
      '<a href="https://preview-abc.pages.dev/x">x</a><a href="https://preview-abc.pages.dev/y">y</a>',
    );
    expect(out).not.toContain(DEFAULT_ORIGIN);
  });

  it('is a no-op when target equals default', () => {
    const input = `canonical: ${DEFAULT_ORIGIN}/`;
    expect(rewriteOrigin(input, DEFAULT_ORIGIN)).toBe(input);
  });

  it('does not partial-match a different domain that contains the default as substring', () => {
    // Verifies split/join doesn't false-positive on something like
    // `prefix-${DEFAULT_ORIGIN}-suffix` — it WOULD match, which is the
    // desired behaviour (string replacement, not boundary-aware). This
    // test pins that behaviour so any future change to boundary-aware
    // logic is intentional.
    const input = `weird-${DEFAULT_ORIGIN}-tail`;
    expect(rewriteOrigin(input, 'https://x.com')).toBe('weird-https://x.com-tail');
  });

  it('leaves unrelated content untouched', () => {
    const input = '<title>Hello</title><meta name="x" content="y">';
    expect(rewriteOrigin(input, 'https://x.com')).toBe(input);
  });
});

describe('rewriteApiBase', () => {
  it('replaces every occurrence of the default API base', () => {
    const input = `<meta property="og:image" content="${DEFAULT_API_BASE}/api/og?brand=1" /><img src="${DEFAULT_API_BASE}/api/og?d=stripe.com">`;
    const out = rewriteApiBase(input, 'https://preview-api.fly.dev');
    expect(out).toContain('https://preview-api.fly.dev/api/og?brand=1');
    expect(out).not.toContain(DEFAULT_API_BASE);
  });

  it('is a no-op when target equals default', () => {
    const input = `image: ${DEFAULT_API_BASE}/api/og?brand=1`;
    expect(rewriteApiBase(input, DEFAULT_API_BASE)).toBe(input);
  });

  it('does not touch DEFAULT_ORIGIN occurrences', () => {
    const input = `${DEFAULT_ORIGIN}/ + ${DEFAULT_API_BASE}/api`;
    const out = rewriteApiBase(input, 'https://other-api.com');
    expect(out).toContain(DEFAULT_ORIGIN);
    expect(out).toContain('https://other-api.com/api');
  });
});

describe('rewriteUpdatedDate', () => {
  const ISO = '2026-05-13';
  const HUMAN = 'May 13, 2026';

  it('rewrites <time datetime="YYYY-MM-DD">visible</time>', () => {
    const input = '<time datetime="2026-05-12">May 12, 2026</time>';
    expect(rewriteUpdatedDate(input, ISO, HUMAN)).toBe(
      '<time datetime="2026-05-13">May 13, 2026</time>',
    );
  });

  it('handles additional attributes on the <time> element', () => {
    const input = '<time class="byline-date" datetime="2025-01-01" aria-label="x">Jan 1, 2025</time>';
    const out = rewriteUpdatedDate(input, ISO, HUMAN);
    expect(out).toContain(`datetime="${ISO}"`);
    expect(out).toContain(HUMAN);
    expect(out).toContain('class="byline-date"');
    expect(out).toContain('aria-label="x"');
  });

  it('rewrites "Updated YYYY-MM-DD" inside a byline class', () => {
    const input = '<p class="byline kicker">Updated 2026-05-12</p>';
    expect(rewriteUpdatedDate(input, ISO, HUMAN)).toBe(
      `<p class="byline kicker">Updated ${HUMAN}</p>`,
    );
  });

  it('rewrites "Updated Month D, YYYY" inside a byline class', () => {
    const input = '<p class="byline">By Linda · Updated May 12, 2026</p>';
    expect(rewriteUpdatedDate(input, ISO, HUMAN)).toBe(
      `<p class="byline">By Linda · Updated ${HUMAN}</p>`,
    );
  });

  it('does NOT rewrite "Updated …" outside a byline class', () => {
    const input = '<p>This page was last Updated May 12, 2026 for reasons</p>';
    // Outside a class="byline" anchor — leave it alone.
    expect(rewriteUpdatedDate(input, ISO, HUMAN)).toBe(input);
  });

  it('does NOT rewrite RFC-9116 Expires lines in security.txt', () => {
    // We don't want to touch security.txt's `Expires: 2027-05-12T...` line.
    const input = 'Contact: x@y.com\nExpires: 2027-05-12T00:00:00.000Z\n';
    expect(rewriteUpdatedDate(input, ISO, HUMAN)).toBe(input);
  });

  it('rewrites multiple <time> elements in one document', () => {
    const input = '<time datetime="2024-01-01">A</time> and <time datetime="2024-02-02">B</time>';
    const out = rewriteUpdatedDate(input, ISO, HUMAN);
    expect(out).toBe(`<time datetime="${ISO}">${HUMAN}</time> and <time datetime="${ISO}">${HUMAN}</time>`);
  });
});

describe('rewriteCopyrightYear', () => {
  it('rewrites a stale year when the byline link follows with rel="author"', () => {
    const input = '© 2025 <a href="https://github.com/x" rel="author noopener" class="under-dot">Linda</a>';
    const out = rewriteCopyrightYear(input, '2027');
    expect(out).toBe(
      '© 2027 <a href="https://github.com/x" rel="author noopener" class="under-dot">Linda</a>',
    );
  });

  it('handles attribute order variations (target before rel, etc.)', () => {
    const input = '© 2024 <a target="_blank" rel="author noopener" href="/me">me</a>';
    expect(rewriteCopyrightYear(input, '2026')).toContain('© 2026');
  });

  it('does NOT rewrite "© YYYY" when no rel="author" link follows', () => {
    // Defensive: don't false-positive on third-party copyright strings in copy.
    const input = '© 2010 ACME Corp, used with permission.';
    expect(rewriteCopyrightYear(input, '2027')).toBe(input);
  });

  it('does NOT rewrite "© YYYY <a>" when the link has no rel="author"', () => {
    const input = '© 2020 <a href="/legal" rel="noopener">Acme</a>';
    expect(rewriteCopyrightYear(input, '2027')).toBe(input);
  });

  it('is a no-op when the year already matches the build year', () => {
    const input = '© 2026 <a rel="author" href="/me">me</a>';
    expect(rewriteCopyrightYear(input, '2026')).toBe(input);
  });
});

describe('rewriteAll', () => {
  it('combines origin + date rewrites in one pass', () => {
    const input = `<a href="${DEFAULT_ORIGIN}/x">x</a><time datetime="2024-01-01">Jan 1</time>`;
    const out = rewriteAll(input, 'https://x.com', '2026-05-13', 'May 13, 2026');
    expect(out).toBe('<a href="https://x.com/x">x</a><time datetime="2026-05-13">May 13, 2026</time>');
  });

  it('also rewrites the copyright year (derived from isoDate)', () => {
    const input = '© 2024 <a href="/me" rel="author noopener">Linda</a>';
    const out = rewriteAll(input, 'https://x.com', '2027-01-15', 'January 15, 2027');
    expect(out).toContain('© 2027');
  });
});

describe('todayIso / todayHuman', () => {
  it('todayIso emits YYYY-MM-DD for a given Date', () => {
    expect(todayIso(new Date('2026-05-13T15:30:00Z'))).toBe('2026-05-13');
  });

  it('todayHuman emits en-US long-month for a given Date', () => {
    // UTC fixed; locale formatting may shift by ±1 day at TZ boundaries.
    // Pin midday UTC so the answer is stable across CI timezones.
    expect(todayHuman(new Date('2026-05-13T12:00:00Z'))).toBe('May 13, 2026');
  });
});
