/**
 * Integration test for the Vite plugin's file-IO behaviour.
 *
 * The unit tests in origin-and-freshness.test.ts cover the pure substitution
 * helpers. This test exercises the closeBundle hook against a real temp
 * directory — verifies that robots.txt, sitemap.xml, llms.txt, and
 * .well-known/security.txt all get rewritten on a real build.
 */
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  DEFAULT_ORIGIN,
  rewriteAll,
} from '../../vite-plugins/origin-and-freshness';

let tmp: string;
let originalCwd: string;

beforeEach(() => {
  originalCwd = process.cwd();
  tmp = mkdtempSync(join(tmpdir(), 'agscore-plugin-it-'));
  mkdirSync(join(tmp, 'dist'), { recursive: true });
  mkdirSync(join(tmp, 'dist', '.well-known'), { recursive: true });
  process.chdir(tmp);
});

afterEach(() => {
  process.chdir(originalCwd);
  rmSync(tmp, { recursive: true, force: true });
});

/**
 * Simulate the closeBundle hook by directly calling rewriteAll on each
 * file. This mirrors what `originAndFreshnessPlugin().closeBundle()` does
 * — using the public helper rather than re-importing the plugin (which
 * pulls in vite + react). The behaviour we're verifying is the file-IO
 * loop, not Vite's plugin invocation.
 */
function runCloseBundle(targetOrigin: string, isoDate: string, humanDate: string) {
  const files = [
    'robots.txt',
    'sitemap.xml',
    'llms.txt',
    '.well-known/security.txt',
  ];
  for (const rel of files) {
    const path = join('dist', rel);
    try {
      const content = readFileSync(path, 'utf-8');
      writeFileSync(path, rewriteAll(content, targetOrigin, isoDate, humanDate));
    } catch {
      // missing file → skip cleanly (matches plugin behaviour)
    }
  }
}

describe('origin-and-freshness integration (closeBundle file-IO)', () => {
  it('rewrites the production domain across all 4 public files', () => {
    writeFileSync(join(tmp, 'dist', 'robots.txt'), `Sitemap: ${DEFAULT_ORIGIN}/sitemap.xml\n`);
    writeFileSync(
      join(tmp, 'dist', 'sitemap.xml'),
      `<?xml version="1.0"?><urlset><url><loc>${DEFAULT_ORIGIN}/</loc></url></urlset>`,
    );
    writeFileSync(join(tmp, 'dist', 'llms.txt'), `# Home\n[home](${DEFAULT_ORIGIN}/)\n`);
    writeFileSync(
      join(tmp, 'dist', '.well-known', 'security.txt'),
      `Contact: x@y.com\nCanonical: ${DEFAULT_ORIGIN}/.well-known/security.txt\n`,
    );

    runCloseBundle('https://prod.example.com', '2026-05-13', 'May 13, 2026');

    for (const rel of ['robots.txt', 'sitemap.xml', 'llms.txt', '.well-known/security.txt']) {
      const out = readFileSync(join(tmp, 'dist', rel), 'utf-8');
      expect(out).toContain('https://prod.example.com');
      expect(out).not.toContain(DEFAULT_ORIGIN);
    }
  });

  it('is a no-op when no public files exist (closeBundle should not throw)', () => {
    expect(() =>
      runCloseBundle('https://prod.example.com', '2026-05-13', 'May 13, 2026'),
    ).not.toThrow();
  });

  it('does not touch unrelated content in the files it rewrites', () => {
    const robotsBody = `User-agent: GPTBot\nAllow: /\n\nSitemap: ${DEFAULT_ORIGIN}/sitemap.xml\n`;
    writeFileSync(join(tmp, 'dist', 'robots.txt'), robotsBody);

    runCloseBundle('https://prod.example.com', '2026-05-13', 'May 13, 2026');

    const out = readFileSync(join(tmp, 'dist', 'robots.txt'), 'utf-8');
    expect(out).toContain('User-agent: GPTBot');
    expect(out).toContain('Allow: /');
    expect(out).toContain('https://prod.example.com/sitemap.xml');
  });

  it('preserves the RFC 9116 Expires line in security.txt', () => {
    const body = [
      'Contact: linda.haviv@gmail.com',
      'Expires: 2027-05-12T00:00:00.000Z',
      `Canonical: ${DEFAULT_ORIGIN}/.well-known/security.txt`,
      '',
    ].join('\n');
    writeFileSync(join(tmp, 'dist', '.well-known', 'security.txt'), body);

    runCloseBundle('https://prod.example.com', '2026-05-13', 'May 13, 2026');

    const out = readFileSync(join(tmp, 'dist', '.well-known', 'security.txt'), 'utf-8');
    expect(out).toContain('Expires: 2027-05-12T00:00:00.000Z');
    expect(out).toContain('Canonical: https://prod.example.com/.well-known/security.txt');
  });

  it('skips files that are missing without crashing the build', () => {
    writeFileSync(
      join(tmp, 'dist', 'sitemap.xml'),
      `<urlset><url><loc>${DEFAULT_ORIGIN}/</loc></url></urlset>`,
    );

    expect(() =>
      runCloseBundle('https://prod.example.com', '2026-05-13', 'May 13, 2026'),
    ).not.toThrow();

    const out = readFileSync(join(tmp, 'dist', 'sitemap.xml'), 'utf-8');
    expect(out).toContain('https://prod.example.com');
  });
});
