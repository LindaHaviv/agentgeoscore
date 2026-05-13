/**
 * Unit tests for the build-time rewriter helpers used by vite.config.ts's
 * origin-and-freshness Vite plugin.
 */
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_ORIGIN,
  rewriteAll,
  rewriteOrigin,
  rewriteUpdatedDate,
  todayHuman,
  todayIso,
} from '../../vite-plugins/origin-and-freshness';

describe('rewriteOrigin', () => {
  it('replaces every occurrence of the default origin', () => {
    const input = `<a href="${DEFAULT_ORIGIN}/x">x</a><a href="${DEFAULT_ORIGIN}/y">y</a>`;
    const out = rewriteOrigin(input, 'https://agentgeoscore.com');
    expect(out).toBe(
      '<a href="https://agentgeoscore.com/x">x</a><a href="https://agentgeoscore.com/y">y</a>',
    );
    expect(out).not.toContain('dist-olcivbch.devinapps.com');
  });

  it('is a no-op when target equals default', () => {
    const input = `canonical: ${DEFAULT_ORIGIN}/`;
    expect(rewriteOrigin(input, DEFAULT_ORIGIN)).toBe(input);
  });

  it('does not partial-match a different domain that contains the default as substring', () => {
    // Verifies split/join doesn't false-positive on something like
    // `prefix-https://dist-olcivbch.devinapps.com-suffix` — it WOULD match,
    // which is the desired behaviour (string replacement, not boundary-aware).
    // This test pins that behaviour so any future change to boundary-aware
    // logic is intentional.
    const input = `weird-${DEFAULT_ORIGIN}-tail`;
    expect(rewriteOrigin(input, 'https://x.com')).toBe('weird-https://x.com-tail');
  });

  it('leaves unrelated content untouched', () => {
    const input = '<title>Hello</title><meta name="x" content="y">';
    expect(rewriteOrigin(input, 'https://x.com')).toBe(input);
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

describe('rewriteAll', () => {
  it('combines origin + date rewrites in one pass', () => {
    const input = `<a href="${DEFAULT_ORIGIN}/x">x</a><time datetime="2024-01-01">Jan 1</time>`;
    const out = rewriteAll(input, 'https://x.com', '2026-05-13', 'May 13, 2026');
    expect(out).toBe('<a href="https://x.com/x">x</a><time datetime="2026-05-13">May 13, 2026</time>');
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
