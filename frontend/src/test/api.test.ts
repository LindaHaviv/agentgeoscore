import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buildShareUrl,
  compareCompetitors,
  fetchTestPromptsForCategory,
  normalizeDomain,
  scanUrl,
} from '../api';

describe('normalizeDomain', () => {
  it('strips scheme', () => {
    expect(normalizeDomain('https://Example.com')).toBe('example.com');
    expect(normalizeDomain('http://example.com')).toBe('example.com');
  });
  it('strips path and query', () => {
    expect(normalizeDomain('example.com/foo?bar=1')).toBe('example.com');
  });
  it('trims whitespace', () => {
    expect(normalizeDomain('  example.com  ')).toBe('example.com');
  });
});

describe('buildShareUrl', () => {
  it('returns the fallback URL when VITE_API_BASE is unset', () => {
    // In test mode VITE_API_BASE is empty → BASE is falsy → fallback path.
    expect(buildShareUrl('stripe.com', 87, 'B', 'http://fallback/')).toBe('http://fallback/');
  });
});

describe('scanUrl', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('throws the API detail message on a 4xx/5xx response', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 502,
      json: async () => ({ detail: 'backend exploded' }),
    });
    await expect(scanUrl('https://stripe.com')).rejects.toThrow(/backend exploded/);
  });

  it('falls back to "HTTP <status>" when the error body is not JSON', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => {
        throw new Error('not json');
      },
    });
    await expect(scanUrl('https://stripe.com')).rejects.toThrow(/HTTP 503/);
  });

  it('returns the parsed Report on success', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ domain: 'stripe.com', score: 87 }),
    });
    const report = await scanUrl('https://stripe.com');
    expect(report).toMatchObject({ domain: 'stripe.com', score: 87 });
  });
});

describe('compareCompetitors', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('passes a target without a scheme through as https://', async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ target: {}, competitors: [] }),
    });
    await compareCompetitors('stripe.com', ['square.com']);
    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.target).toBe('https://stripe.com');
  });

  it('passes a target with a scheme through unchanged', async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ target: {}, competitors: [] }),
    });
    await compareCompetitors('http://stripe.com', ['square.com']);
    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.target).toBe('http://stripe.com');
  });

  it('surfaces the API error message on failure', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'compare crashed' }),
    });
    await expect(compareCompetitors('stripe.com', ['square.com'])).rejects.toThrow(
      /compare crashed/,
    );
  });

  it('falls back to "HTTP <status>" when error body is not JSON', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 504,
      json: async () => {
        throw new Error('not json');
      },
    });
    await expect(compareCompetitors('stripe.com', ['square.com'])).rejects.toThrow(/HTTP 504/);
  });
});

describe('fetchTestPromptsForCategory', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the bundle on success', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ brand: 'Stripe', prompts: [] }),
    });
    const bundle = await fetchTestPromptsForCategory('stripe.com', 'fintech');
    expect(bundle).toMatchObject({ brand: 'Stripe' });
  });

  it('throws the API detail message on failure', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'bad category' }),
    });
    await expect(fetchTestPromptsForCategory('stripe.com', 'bogus')).rejects.toThrow(
      /bad category/,
    );
  });

  it('falls back to "HTTP <status>" when error body is not JSON', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 429,
      json: async () => {
        throw new Error('not json');
      },
    });
    await expect(fetchTestPromptsForCategory('stripe.com', 'fintech')).rejects.toThrow(
      /HTTP 429/,
    );
  });
});
