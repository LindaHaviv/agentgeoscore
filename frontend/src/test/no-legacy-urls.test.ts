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
  '*.sh',
];

// Files that legitimately reference the legacy URL (e.g. as a must-not-contain
// regression check). Listed as git pathspec exclude patterns so the scan
// passes by ignoring them. Keep this list minimal — every entry should have
// a comment explaining why the literal needs to be there.
const EXCLUDED_PATHS = [
  // The precheck script asserts /share HTML does NOT reference the legacy
  // host post-cutover — the negative-assertion needs the literal in source.
  ':(exclude)scripts/precheck-cutover.sh',
  // This test file itself has the legacy host as a LEGACY_HOSTS const.
  ':(exclude)frontend/src/test/no-legacy-urls.test.ts',
];

describe('no-legacy-urls regression guard', () => {
  for (const host of LEGACY_HOSTS) {
    it(`'${host}' must not appear in tracked source files`, () => {
      // Pathspecs follow the `--` separator. Include the file-extension
      // globs and the exclude patterns in the same pathspec list — git
      // intersects them so excluded paths don't match even if their
      // extension does.
      const pathspecs = [...SCAN_GLOBS, ...EXCLUDED_PATHS]
        .map((p) => `'${p}'`)
        .join(' ');
      let out = '';
      try {
        // `git grep` exits 1 when no matches — that's the success case for
        // us. Capture stdout either way and assert on it.
        out = execSync(
          `git grep -nF '${host}' -- ${pathspecs}`,
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
