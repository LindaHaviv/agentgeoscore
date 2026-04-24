import type { Report } from './types';

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

/** Base URL for the backend — exposed so share links resolve against the API origin. */
export const API_BASE = BASE;

/**
 * Build a shareable URL for a report. Points at the backend `/share` route,
 * which renders the OG meta tags crawlers need and then redirects humans to
 * the SPA `/report/<domain>` page. Falls back to the raw SPA URL if the API
 * base isn't configured (e.g. local dev without VITE_API_BASE set).
 */
export function buildShareUrl(
  domain: string,
  score: number,
  grade: string,
  fallbackUrl: string,
): string {
  if (!BASE) return fallbackUrl;
  const qs = new URLSearchParams({ d: domain, s: String(score), g: grade });
  return `${BASE.replace(/\/$/, '')}/share?${qs.toString()}`;
}

export async function scanUrl(url: string): Promise<Report> {
  const resp = await fetch(`${BASE}/api/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, include_probe: true }),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return (await resp.json()) as Report;
}

export function normalizeDomain(input: string): string {
  const cleaned = input.trim().replace(/^https?:\/\//, '').replace(/\/.*$/, '');
  return cleaned.toLowerCase();
}
