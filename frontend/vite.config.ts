import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';
import {
  DEFAULT_API_BASE,
  DEFAULT_ORIGIN,
  rewriteAll,
  todayHuman,
  todayIso,
} from './vite-plugins/origin-and-freshness';

/**
 * Rewrites every literal `DEFAULT_ORIGIN` (production frontend URL) and
 * `DEFAULT_API_BASE` (production backend URL) occurrence in the built HTML
 * and the copied `public/` files to whatever `VITE_FRONTEND_ORIGIN` and
 * `VITE_API_BASE` (or their fallbacks) are. Also rewrites the byline
 * `<time datetime>` + visible "Updated …" date to today.
 *
 * Pure substitution logic lives in build/origin-and-freshness.ts so it can
 * be unit-tested in isolation; this plugin is the Vite-side glue.
 */
function originAndFreshnessPlugin(): Plugin {
  // Fail loud on production builds missing either of the two required env
  // vars. Without VITE_FRONTEND_ORIGIN the built artifact silently ships the
  // placeholder in og:url / canonical / JSON-LD / sitemap. Without
  // VITE_API_BASE the runtime fetch in src/api.ts falls back to same-origin
  // and the homepage scan form 404s on Cloudflare Pages (no /api proxy).
  // The HTML rewriter masks the API base in static metadata via
  // DEFAULT_API_BASE, so the bug is invisible to view-source — gate at
  // build time instead.
  if (process.env.NODE_ENV === 'production') {
    const missing: string[] = [];
    if (!process.env.VITE_FRONTEND_ORIGIN) missing.push('VITE_FRONTEND_ORIGIN');
    if (!process.env.VITE_API_BASE) missing.push('VITE_API_BASE');
    if (missing.length > 0) {
      throw new Error(
        `${missing.join(' and ')} must be set for production builds. ` +
          'Set on the host (e.g. Cloudflare Pages → Environment variables): ' +
          'VITE_FRONTEND_ORIGIN=https://agentgeoscore.com, ' +
          'VITE_API_BASE=https://api.agentgeoscore.com.',
      );
    }
  }
  const targetOrigin = (process.env.VITE_FRONTEND_ORIGIN || DEFAULT_ORIGIN).replace(/\/$/, '');
  const targetApiBase = (process.env.VITE_API_BASE || DEFAULT_API_BASE).replace(/\/$/, '');
  const now = new Date();
  const isoDate = todayIso(now);
  const humanDate = todayHuman(now);
  const apply = (s: string) =>
    rewriteAll(s, targetOrigin, isoDate, humanDate, targetApiBase);

  return {
    name: 'agentgeoscore-origin-and-freshness',
    transformIndexHtml(html) {
      return apply(html);
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
          writeFileSync(path, apply(content));
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
