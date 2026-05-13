import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';
import {
  DEFAULT_ORIGIN,
  rewriteAll,
  todayHuman,
  todayIso,
} from './vite-plugins/origin-and-freshness';

/**
 * Rewrites every literal `https://dist-olcivbch.devinapps.com` occurrence in
 * the built HTML and the copied `public/` files to whatever
 * `VITE_FRONTEND_ORIGIN` (or its fallback) is. Also rewrites the byline
 * `<time datetime>` + visible "Updated …" date to today.
 *
 * Pure substitution logic lives in build/origin-and-freshness.ts so it can
 * be unit-tested in isolation; this plugin is the Vite-side glue.
 */
function originAndFreshnessPlugin(): Plugin {
  // Fail loud on production builds without an explicit VITE_FRONTEND_ORIGIN —
  // otherwise the built artifact silently ships the devinapps placeholder in
  // og:url, canonical, JSON-LD @id, and sitemap.xml, which then pollutes any
  // share preview or AI-crawler index that scrapes the production deploy.
  if (process.env.NODE_ENV === 'production' && !process.env.VITE_FRONTEND_ORIGIN) {
    throw new Error(
      'VITE_FRONTEND_ORIGIN must be set for production builds. ' +
        'Set it on the host (e.g. Cloudflare Pages → Environment variables) to ' +
        'the public site origin (e.g. https://agentgeoscore.com).',
    );
  }
  const targetOrigin = (process.env.VITE_FRONTEND_ORIGIN || DEFAULT_ORIGIN).replace(/\/$/, '');
  const now = new Date();
  const isoDate = todayIso(now);
  const humanDate = todayHuman(now);
  const apply = (s: string) => rewriteAll(s, targetOrigin, isoDate, humanDate);

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
