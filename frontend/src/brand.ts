/**
 * Single source of truth for product-facing branding strings.
 *
 * Anything a rename would need to touch (tweet template, footer kicker,
 * header wordmark, og:title, …) reads from here.
 */
export const BRAND = {
  name: 'AgentGEOScore',
  short: 'GEOScore',
  tagline: 'Generative Engine Optimization, graded.',
  repoUrl: 'https://github.com/LindaHaviv/agentgeoscore',
  tweetTemplate: (domain: string, score: number, grade: string, url: string) =>
    `${domain} scored ${score}/100 (${grade}) on ${BRAND.name} — ${BRAND.tagline} ${url}`,
} as const;
