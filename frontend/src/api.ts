import type { Report } from './types';

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

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
