/**
 * Recommendations we can't statically score from one HTTP fetch but that the
 * research consistently flags as high-leverage GEO signals.
 *
 * Sources:
 *   - Princeton/IIT-Delhi GEO paper (Aggarwal et al., KDD 2024,
 *     arXiv:2311.09735): empirically tested content modifications.
 *   - Google E-E-A-T Quality Rater Guidelines (canonical authority signals).
 *   - Perplexity public source-selection writeups (RAG retrieval gates).
 *
 * These appear here, separated from the scored fix list, so users get the
 * full picture without the score punishing things we can't measure
 * objectively.
 */

interface Recommendation {
  title: string;
  body: string;
  evidence: string;
}

const RECOMMENDATIONS: Recommendation[] = [
  {
    title: 'Publish original data — even small samples',
    body: 'Run a poll on your audience, pull stats from your product analytics, or publish "what we saw across X customers." Anything with a number nobody else has is disproportionately citable. AI engines preferentially cite content with statistics they can\'t source elsewhere.',
    evidence: 'Princeton GEO 2024: "Statistics Addition" raised citation visibility ~30%.',
  },
  {
    title: 'Show up authentically on Reddit and GitHub',
    body: 'Find threads where your topic comes up and answer thoroughly without pitching. AI systems treat reddit.com and github.com as trusted sources, so your name (or your product\'s name) appearing in a high-quality thread carries weight even with no link back.',
    evidence: 'Perplexity, Brave, and Google AI Overviews all index Reddit/GitHub threads heavily as primary sources.',
  },
  {
    title: 'Refresh content substantively, not just the date',
    body: 'When you update a post, change something real — add new data, swap stale examples, or rewrite a section. AI engines look at content delta alongside dateModified. A bumped date with no body changes can be detected and ignored.',
    evidence: 'Schema.org dateModified spec; Perplexity / Google AI Overviews freshness signals.',
  },
  {
    title: 'Write in an authoritative, declarative tone',
    body: 'Hedged language ("might be", "could possibly", "in some cases") gets paraphrased away. Direct, declarative sentences with concrete claims are more likely to be quoted verbatim. Princeton called this "Authoritative" and showed it lifts citations across most domains.',
    evidence: 'Princeton GEO 2024: "Authoritative" tone modification was a top-3 lever.',
  },
  {
    title: 'Earn mentions on third-party authority sites',
    body: 'Get listed in industry roundups, comparison pages, "best of" lists, and analyst reports. AI engines verify your claims against external sources before citing — being mentioned by sites the AI already trusts (G2, TechCrunch, your industry\'s top blogs) makes you eligible for citation.',
    evidence: 'E-E-A-T Trustworthiness signal; consistently flagged across Perplexity / OpenAI / Anthropic source-selection docs.',
  },
  {
    title: 'Optional: experiment with /llms.txt — but write it yourself',
    body: 'Some tools publish an /llms.txt Markdown summary describing their site for LLMs (proposal at llmstxt.org). No major AI engine has publicly confirmed it reads this file yet, so we don\'t score it. If you want to try it, write one yourself in your own voice — don\'t paste a template. The point is to articulate what your site is about; a generic auto-generated file adds noise, not signal.',
    evidence: 'llmstxt.org spec; unadopted by OpenAI / Anthropic / Google AI / Perplexity as of 2026.',
  },
];

export function RecommendationsCard() {
  return (
    <div className="paper-card p-6 sm:p-8">
      <div className="mb-5 sm:mb-6">
        <div className="kicker mb-1.5">bonus · what we can&apos;t score</div>
        <h3 className="font-display text-2xl sm:text-3xl text-ink-900 tracking-tightish leading-tight">
          Off-page signals worth your time.
        </h3>
        <p className="text-ink-700 text-sm leading-relaxed mt-3 max-w-2xl">
          These are real GEO levers we can&apos;t measure from a single page
          fetch — but the research consistently flags them as high-leverage.
          They don&apos;t affect your score; they affect your citations.
        </p>
      </div>
      <ul className="divide-y divide-rule">
        {RECOMMENDATIONS.map((rec) => (
          <li key={rec.title} className="py-4 sm:py-5">
            <h4 className="font-display text-base sm:text-lg text-ink-900 tracking-tightish mb-1.5">
              {rec.title}
            </h4>
            <p className="text-ink-700 text-sm leading-relaxed">{rec.body}</p>
            <p className="text-ink-500 text-xs leading-relaxed mt-2 font-mono">
              {rec.evidence}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
