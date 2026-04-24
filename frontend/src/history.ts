import type { Report } from './types';

export interface HistoryEntry {
  domain: string;
  score: number;
  grade: string;
  scannedAt: string;
  durationMs: number;
  categoryCount: number;
  fixCount: number;
}

const STORAGE_KEY = 'agentgeoscore:history';
const REPORT_PREFIX = 'agentgeoscore:report:';
const MAX_ENTRIES = 30;

function readEntries(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeEntries(entries: HistoryEntry[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
}

export function saveReport(report: Report): void {
  const entry: HistoryEntry = {
    domain: report.domain,
    score: report.score,
    grade: report.grade,
    scannedAt: report.scanned_at,
    durationMs: report.duration_ms,
    categoryCount: report.categories.length,
    fixCount: report.fixes.length,
  };

  const entries = readEntries().filter((e) => e.domain !== report.domain);
  entries.unshift(entry);
  const evicted = entries.slice(MAX_ENTRIES);
  for (const e of evicted) {
    localStorage.removeItem(REPORT_PREFIX + e.domain);
  }
  writeEntries(entries.slice(0, MAX_ENTRIES));

  localStorage.setItem(REPORT_PREFIX + report.domain, JSON.stringify(report));
}

export function getHistory(): HistoryEntry[] {
  return readEntries();
}

export function getCachedReport(domain: string): Report | null {
  try {
    const raw = localStorage.getItem(REPORT_PREFIX + domain);
    if (!raw) return null;
    return JSON.parse(raw) as Report;
  } catch {
    return null;
  }
}

export function clearHistory(): void {
  const entries = readEntries();
  for (const entry of entries) {
    localStorage.removeItem(REPORT_PREFIX + entry.domain);
  }
  localStorage.removeItem(STORAGE_KEY);
}

export function removeEntry(domain: string): void {
  const entries = readEntries().filter((e) => e.domain !== domain);
  writeEntries(entries);
  localStorage.removeItem(REPORT_PREFIX + domain);
}

export function formatRelativeTime(isoDate: string): string {
  const now = Date.now();
  const then = new Date(isoDate).getTime();
  const diff = now - then;
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(isoDate).toLocaleDateString();
}
