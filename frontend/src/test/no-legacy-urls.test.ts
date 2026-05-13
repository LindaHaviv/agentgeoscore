/**
 * Regression guard: the legacy preview-domain URL must never reappear in
 * tracked sources. Was the cutover placeholder before #45 flipped
 * DEFAULT_ORIGIN to the production host; if someone reintroduces it (e.g.
 * by copying a stale snippet back), this test fails the build.
 *
 * Runs `git grep` from the repo root, scoped to file extensions where a
 * URL would actually do harm at runtime / build time (excludes Markdown
 * histories like CHANGELOG that may reference the legacy URL by design).
 */
import { execSync } from 'node:child_process';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const REPO_ROOT = resolve(__dirname, '..', '..', '..');
const LEGACY_HOSTS = ['dist-olcivbch.devinapps.com'];
const SCAN_GLOBS = [
  '*.ts',
  '*.tsx',
  '*.js',
  '*.jsx',
  '*.html',
  '*.py',
  '*.json',
  '*.toml',
  '*.yml',
  '*.yaml',
  '*.txt',
  '*.xml',
];

describe('no-legacy-urls regression guard', () => {
  for (const host of LEGACY_HOSTS) {
    it(`'${host}' must not appear in tracked source files`, () => {
      const globArgs = SCAN_GLOBS.flatMap((g) => ['--', g]);
      let out = '';
      try {
        // `git grep` exits 1 when no matches — that's the success case for
        // us. Capture stdout either way and assert on it.
        out = execSync(
          `git grep -nF '${host}' ${globArgs.map((a) => `'${a}'`).join(' ')}`,
          { cwd: REPO_ROOT, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] },
        ).toString();
      } catch (e: unknown) {
        // Exit code 1 = no matches found, which is what we want.
        const status = (e as { status?: number }).status;
        if (status !== 1) throw e;
      }
      expect(
        out,
        `Legacy URL '${host}' found in tracked sources:\n${out}\n` +
          'If you intentionally need to reference the legacy host (e.g. in a ' +
          'CHANGELOG entry documenting the cutover), keep it in a .md file ' +
          'and update this test\'s SCAN_GLOBS to skip that extension.',
      ).toBe('');
    });
  }
});
