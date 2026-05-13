/**
 * Regression guard for the static SEO shell in ../../index.html.
 *
 * Every assertion below corresponds to a check the backend scorer runs.
 * If anyone edits index.html in a way that drops one of these, the test
 * fails and the score regresses *before* hitting prod.
 *
 * Keep this aligned with backend/app/scanners/{content_clarity,structured_data,citability,js_rendering}.py.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const html = readFileSync(resolve(__dirname, '..', '..', 'index.html'), 'utf8');
const doc = new DOMParser().parseFromString(html, 'text/html');

function jsonldBlocks(): Array<Record<string, unknown>> {
  const scripts = Array.from(doc.querySelectorAll('script[type="application/ld+json"]'));
  return scripts.flatMap((s) => {
    const raw = (s.textContent || '').trim();
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [parsed];
    } catch {
      return [];
    }
  });
}

describe('SEO shell — head metadata', () => {
  it('has a 10–70 char <title>', () => {
    const title = (doc.querySelector('title')?.textContent || '').trim();
    expect(title.length).toBeGreaterThanOrEqual(10);
    expect(title.length).toBeLessThanOrEqual(70);
  });

  it('has a 50–170 char meta description', () => {
    const desc = doc.querySelector('meta[name="description"]')?.getAttribute('content') || '';
    expect(desc.length).toBeGreaterThanOrEqual(50);
    expect(desc.length).toBeLessThanOrEqual(170);
  });

  it('declares a canonical URL', () => {
    const href = doc.querySelector('link[rel="canonical"]')?.getAttribute('href');
    expect(href).toMatch(/^https?:\/\//);
  });

  it('links to a manifest', () => {
    expect(doc.querySelector('link[rel="manifest"]')).not.toBeNull();
  });

  it('declares <html lang>', () => {
    expect(doc.documentElement.getAttribute('lang')).toBeTruthy();
  });

  it('declares all 5 core OpenGraph properties', () => {
    for (const prop of ['og:title', 'og:description', 'og:type', 'og:url', 'og:image']) {
      const tag = doc.querySelector(`meta[property="${prop}"]`);
      expect(tag, `missing ${prop}`).not.toBeNull();
      expect(tag?.getAttribute('content')?.length || 0, `empty ${prop}`).toBeGreaterThan(0);
    }
  });

  it('declares twitter:card', () => {
    expect(doc.querySelector('meta[name="twitter:card"]')?.getAttribute('content')).toBe(
      'summary_large_image',
    );
  });
});

describe('SEO shell — JSON-LD blocks', () => {
  const blocks = jsonldBlocks();

  it('parses every JSON-LD <script> as valid JSON', () => {
    const scripts = doc.querySelectorAll('script[type="application/ld+json"]');
    expect(scripts.length).toBeGreaterThanOrEqual(5);
    // jsonldBlocks() silently drops invalid blocks; counts must match.
    expect(blocks.length).toBe(scripts.length);
  });

  it('ships WebSite, Organization, SoftwareApplication, Person, FAQPage at minimum', () => {
    const types = blocks.map((b) => b['@type']).filter(Boolean) as string[];
    for (const t of [
      'WebSite',
      'Organization',
      'SoftwareApplication',
      'Person',
      'FAQPage',
    ]) {
      expect(types, `${t} JSON-LD missing`).toContain(t);
    }
  });

  it('Organization has name + url + sameAs', () => {
    const org = blocks.find((b) => b['@type'] === 'Organization') as
      | Record<string, unknown>
      | undefined;
    expect(org).toBeDefined();
    expect(org?.name).toBeTruthy();
    expect(org?.url).toBeTruthy();
    expect(Array.isArray(org?.sameAs) && (org!.sameAs as unknown[]).length).toBeGreaterThan(0);
  });

  it('Person has ≥2 sameAs links (E-E-A-T strong signal)', () => {
    const person = blocks.find((b) => b['@type'] === 'Person') as
      | Record<string, unknown>
      | undefined;
    expect(person).toBeDefined();
    const sameAs = person?.sameAs as unknown;
    const list = Array.isArray(sameAs) ? sameAs : sameAs ? [sameAs] : [];
    expect(list.length).toBeGreaterThanOrEqual(2);
  });

  it('FAQPage mainEntity is an array of well-formed Question/Answer pairs', () => {
    const faq = blocks.find((b) => b['@type'] === 'FAQPage') as
      | Record<string, unknown>
      | undefined;
    expect(faq).toBeDefined();
    const mainEntity = faq?.mainEntity as unknown[];
    expect(Array.isArray(mainEntity)).toBe(true);
    expect(mainEntity.length).toBeGreaterThanOrEqual(3);
    for (const q of mainEntity as Array<Record<string, unknown>>) {
      expect(q['@type']).toBe('Question');
      expect(q.name).toBeTruthy();
      const ans = q.acceptedAnswer as Record<string, unknown> | undefined;
      expect(ans?.['@type']).toBe('Answer');
      expect(typeof ans?.text === 'string' && (ans!.text as string).length > 0).toBe(true);
    }
  });

  it('SoftwareApplication has required + recommended props', () => {
    const app = blocks.find((b) => b['@type'] === 'SoftwareApplication') as
      | Record<string, unknown>
      | undefined;
    expect(app).toBeDefined();
    expect(app?.name).toBeTruthy();
    expect(app?.applicationCategory).toBeTruthy();
    expect(app?.operatingSystem).toBeTruthy();
    expect(app?.offers).toBeDefined();
  });
});

describe('SEO shell — semantic HTML in pre-React body', () => {
  it('has exactly one <h1>', () => {
    expect(doc.querySelectorAll('h1').length).toBe(1);
  });

  it('has all 5 semantic landmarks (header/main/nav/footer/article)', () => {
    for (const tag of ['header', 'main', 'nav', 'footer', 'article']) {
      expect(doc.querySelector(tag), `<${tag}> missing`).not.toBeNull();
    }
  });

  it('has H2 and H3 subheadings', () => {
    expect(doc.querySelectorAll('h2').length).toBeGreaterThan(0);
    expect(doc.querySelectorAll('h3').length).toBeGreaterThan(0);
  });

  it('ships ≥800 chars of visible text in <body> (clears js_rendering threshold)', () => {
    // Mirror the scanner: strip script/style/noscript before counting.
    const body = doc.body.cloneNode(true) as HTMLElement;
    body.querySelectorAll('script, style, noscript, template').forEach((el) => el.remove());
    const text = (body.textContent || '').replace(/\s+/g, ' ').trim();
    expect(text.length).toBeGreaterThanOrEqual(800);
  });

  it('has a byline anchor with rel="author"', () => {
    const byline = doc.querySelector('a[rel="author"]');
    expect(byline).not.toBeNull();
    expect(byline?.getAttribute('href')).toMatch(/^https?:\/\//);
  });

  it('has a <time datetime> element (freshness signal)', () => {
    const time = doc.querySelector('time[datetime]');
    expect(time).not.toBeNull();
    expect(time?.getAttribute('datetime')).toMatch(/^\d{4}-\d{2}-\d{2}/);
  });

  it('has a visible "Updated …" line (paired with the <time> for full E-E-A-T credit)', () => {
    const text = (doc.body.textContent || '').replace(/\s+/g, ' ');
    expect(text).toMatch(
      /\b(?:updated|last updated|last modified|modified|published)\b[\s:.-]*[A-Za-z0-9,\s/-]+/i,
    );
  });
});

describe('SEO shell — citability signals inside the main <article>', () => {
  const article = doc.querySelector('article')!;

  it('has ≥3 distinct outbound citation domains', () => {
    const hrefs = Array.from(article.querySelectorAll('a[href]'))
      .map((a) => a.getAttribute('href') || '')
      .filter((h) => /^https?:\/\//.test(h));
    const domains = new Set<string>();
    for (const h of hrefs) {
      try {
        const host = new URL(h).host.toLowerCase().replace(/^www\./, '');
        const parts = host.split('.');
        const registered = parts.length > 2 ? parts.slice(-2).join('.') : host;
        // Drop self-references so the outbound-domain count is honest.
        if (registered === 'agentgeoscore.com') continue;
        domains.add(registered);
      } catch {
        // ignore malformed URLs
      }
    }
    expect(domains.size).toBeGreaterThanOrEqual(3);
  });

  it('cites the Princeton GEO paper at arxiv.org', () => {
    const href = Array.from(article.querySelectorAll('a[href]'))
      .map((a) => a.getAttribute('href') || '')
      .find((h) => h.includes('arxiv.org'));
    expect(href).toBeTruthy();
  });

  it('has ≥2 quotation elements (blockquote/q/cite)', () => {
    const total =
      article.querySelectorAll('blockquote').length +
      article.querySelectorAll('q').length +
      article.querySelectorAll('cite').length;
    expect(total).toBeGreaterThanOrEqual(2);
  });

  it('has quantitative claims (percentages or year tokens)', () => {
    const text = (article.textContent || '').replace(/\s+/g, ' ');
    const percents = text.match(/\d+%/g) || [];
    const years = text.match(/\b(?:19|20)\d{2}\b/g) || [];
    expect(percents.length + years.length).toBeGreaterThanOrEqual(4);
  });

  it('has at least 2 question-shaped H2/H3 (fan-out chunking signal)', () => {
    const headings = Array.from(article.querySelectorAll('h2, h3'));
    const qs = headings.filter((h) => (h.textContent || '').trim().endsWith('?'));
    expect(qs.length).toBeGreaterThanOrEqual(2);
  });
});
