import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

// Fallback used when `VITE_FRONTEND_ORIGIN` is unset. This is the URL the
// repo's static SEO surface was authored against; replacing it at build
// time lets us flip the production domain via a single env var without
// touching source files.
const DEFAULT_ORIGIN = 'https://dist-olcivbch.devinapps.com';

/**
 * Rewrites every literal `https://dist-olcivbch.devinapps.com` occurrence in
 * the built HTML and the copied `public/` files to whatever
 * `VITE_FRONTEND_ORIGIN` (or its fallback) is.
 *
 * Why this exists:
 *
 *  - `frontend/index.html` ships a static SEO shell with hardcoded canonical /
 *    og:url / JSON-LD URLs. AI crawlers see them before React hydrates.
 *  - `frontend/public/{robots.txt,sitemap.xml,llms.txt,.well-known/security.txt}`
 *    each reference the same domain.
 *  - Source files keep the literal URL so they round-trip cleanly in tests
 *    and don't depend on env state. Cutover is one env-var change.
 *
 * Also rewrites the `<time datetime="…">` byline freshness signal to today's
 * date on each production build, so the page never advertises a stale
 * "Updated" date.
 */
function originAndFreshnessPlugin(): Plugin {
  const targetOrigin = (process.env.VITE_FRONTEND_ORIGIN || DEFAULT_ORIGIN).replace(/\/$/, '');
  const today = new Date().toISOString().slice(0, 10);
  const todayHuman = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  const replaceOrigin = (s: string) =>
    s.split(DEFAULT_ORIGIN).join(targetOrigin);

  const replaceTime = (s: string) =>
    s
      // <time datetime="YYYY-MM-DD">Month D, YYYY</time>  →  today
      .replace(
        /<time datetime="\d{4}-\d{2}-\d{2}">[^<]+<\/time>/g,
        `<time datetime="${today}">${todayHuman}</time>`,
      )
      // Plain-text fallback: "Updated 2026-05-12" in non-HTML files
      .replace(
        /Updated\s+(?:\d{4}-\d{2}-\d{2}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})/g,
        `Updated ${todayHuman}`,
      );

  return {
    name: 'agentgeoscore-origin-and-freshness',
    transformIndexHtml(html) {
      return replaceTime(replaceOrigin(html));
    },
    closeBundle() {
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
          writeFileSync(path, replaceTime(replaceOrigin(content)));
        } catch {
          // File not present in this build — skip cleanly.
        }
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), originAndFreshnessPlugin()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Playwright e2e specs live under tests/e2e/ and must not be loaded by vitest.
    exclude: ['**/node_modules/**', '**/dist/**', '**/tests/e2e/**'],
  },
});
