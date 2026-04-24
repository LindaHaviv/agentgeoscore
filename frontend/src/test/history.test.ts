import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  clearHistory,
  formatRelativeTime,
  getCachedReport,
  getHistory,
  removeEntry,
  saveReport,
} from '../history';
import type { Report } from '../types';

function makeReport(overrides: Partial<Report> = {}): Report {
  return {
    url: 'https://example.com',
    normalized_url: 'https://example.com/',
    domain: 'example.com',
    scanned_at: new Date().toISOString(),
    duration_ms: 500,
    score: 72,
    grade: 'C',
    categories: [
      { id: 'agent_access', label: 'Agent Access', weight: 0.25, score: 80, checks: [], summary: '' },
      { id: 'discoverability', label: 'Discoverability', weight: 0.2, score: 60, checks: [], summary: '' },
    ],
    fixes: [
      {
        severity: 'critical',
        category: 'discoverability',
        title: 'Add llms.txt',
        detail: 'No llms.txt found',
        score_lift: 8,
        effort: 'low',
      },
    ],
    suggested_llms_txt: '# Example\n> A site',
    errors: [],
    ...overrides,
  };
}

describe('history', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('saves and retrieves a report', () => {
    const report = makeReport();
    saveReport(report);
    const entries = getHistory();
    expect(entries).toHaveLength(1);
    expect(entries[0].domain).toBe('example.com');
    expect(entries[0].score).toBe(72);
    expect(entries[0].grade).toBe('C');
    expect(entries[0].fixCount).toBe(1);
  });

  it('caches the full report object', () => {
    const report = makeReport();
    saveReport(report);
    const cached = getCachedReport('example.com');
    expect(cached).not.toBeNull();
    expect(cached?.score).toBe(72);
    expect(cached?.fixes).toHaveLength(1);
  });

  it('replaces existing entry for same domain', () => {
    saveReport(makeReport({ score: 50, grade: 'D' }));
    saveReport(makeReport({ score: 80, grade: 'B' }));
    const entries = getHistory();
    expect(entries).toHaveLength(1);
    expect(entries[0].score).toBe(80);
  });

  it('keeps most recent entry first', () => {
    saveReport(makeReport({ domain: 'a.com' }));
    saveReport(makeReport({ domain: 'b.com' }));
    saveReport(makeReport({ domain: 'c.com' }));
    const entries = getHistory();
    expect(entries.map((e) => e.domain)).toEqual(['c.com', 'b.com', 'a.com']);
  });

  it('removes a single entry', () => {
    saveReport(makeReport({ domain: 'a.com' }));
    saveReport(makeReport({ domain: 'b.com' }));
    removeEntry('a.com');
    expect(getHistory()).toHaveLength(1);
    expect(getHistory()[0].domain).toBe('b.com');
    expect(getCachedReport('a.com')).toBeNull();
  });

  it('clears all history', () => {
    saveReport(makeReport({ domain: 'a.com' }));
    saveReport(makeReport({ domain: 'b.com' }));
    clearHistory();
    expect(getHistory()).toHaveLength(0);
    expect(getCachedReport('a.com')).toBeNull();
    expect(getCachedReport('b.com')).toBeNull();
  });

  it('limits to 30 entries', () => {
    for (let i = 0; i < 35; i++) {
      saveReport(makeReport({ domain: `site${i}.com` }));
    }
    expect(getHistory()).toHaveLength(30);
  });

  it('handles corrupted localStorage gracefully', () => {
    localStorage.setItem('agentgeoscore:history', 'NOT JSON');
    expect(getHistory()).toEqual([]);
  });
});

describe('formatRelativeTime', () => {
  it('returns "just now" for recent timestamps', () => {
    const now = new Date().toISOString();
    expect(formatRelativeTime(now)).toBe('just now');
  });

  it('returns minutes for timestamps within the hour', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelativeTime(fiveMinAgo)).toBe('5m ago');
  });

  it('returns hours for timestamps within the day', () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(threeHoursAgo)).toBe('3h ago');
  });

  it('returns days for timestamps within the month', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(twoDaysAgo)).toBe('2d ago');
  });
});
