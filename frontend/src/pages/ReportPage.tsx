import { ReactNode, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { CHAPTER_BODY_DELAY_MS, CHAPTER_HEADING_DELAY_MS } from '../animation';
import { buildShareUrl, scanUrl } from '../api';
import { BRAND } from '../brand';
import { CategoryBreakdown } from '../components/CategoryBreakdown';
import { CompetitorCompareCard } from '../components/CompetitorCompareCard';
import { FixList } from '../components/FixList';
import { RecommendationsCard } from '../components/RecommendationsCard';
import { ScanningIndicator } from '../components/ScanningIndicator';
import { ScoreCard } from '../components/ScoreCard';
import { TestPromptsCard } from '../components/TestPromptsCard';
import { URLInput } from '../components/URLInput';
import { useInView } from '../hooks/useInView';
import type { Report } from '../types';

export default function ReportPage() {
  const { domain = '' } = useParams();
  const navigate = useNavigate();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setReport(null);
    setError(null);
    const decoded = decodeURIComponent(domain);
    const hasScheme = /^https?:\/\//i.test(decoded);
    const url = hasScheme ? decoded : `https://${decoded}`;
    scanUrl(url)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [domain]);

  return (
    <section className="px-6 sm:px-10 py-10 max-w-4xl mx-auto">
      <div className="mb-12">
        <URLInput
          compact
          initial={decodeURIComponent(domain)}
          disabled={loading}
          onSubmit={(raw) => {
            const clean = raw.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
            navigate(`/report/${encodeURIComponent(clean)}`);
          }}
        />
      </div>

      {loading && <ScanningIndicator url={decodeURIComponent(domain)} />}

      {error && !loading && (
        <div className="paper-card p-8 border-grade-f/40">
          <div className="kicker text-grade-f mb-2">unable to scan</div>
          <div className="font-display text-2xl text-ink-900 mb-2">
            We couldn't reach {decodeURIComponent(domain)}.
          </div>
          <div className="text-ink-500 text-sm font-mono">{error}</div>
        </div>
      )}

      {report && !loading && (
        <div>
          <ScoreCard report={report} />

          <Chapter title="chapter — the breakdown">
            <CategoryBreakdown categories={report.categories} />
          </Chapter>

          <Chapter
            title={
              <>
                chapter — what to fix, in order{' '}
                <span className="text-ink-300">({report.fixes.length})</span>
              </>
            }
          >
            <FixList items={report.fixes} />
          </Chapter>

          {report.test_prompts && (
            <Chapter title="chapter — test it yourself">
              <TestPromptsCard
                bundle={report.test_prompts}
                domain={report.domain}
              />
            </Chapter>
          )}

          <Chapter title="chapter — versus your competitors">
            <CompetitorCompareCard target={report.domain} />
          </Chapter>

          <Chapter title="chapter — off-page signals">
            <RecommendationsCard />
          </Chapter>

          {report.errors.length > 0 && (
            <div className="mt-10 font-mono text-xs text-ink-400">
              Scan produced {report.errors.length} non-fatal warning(s).
            </div>
          )}

          <div className="mt-20">
            <div className="rule mb-6" />
            <ShareBar report={report} />
          </div>
        </div>
      )}
    </section>
  );
}

function Chapter({ title, children }: { title: ReactNode; children: ReactNode }) {
  const { ref, shown } = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className="mt-16">
      <div
        className={`rule mb-8 origin-left ${shown ? 'animate-rule-draw-fast' : 'scale-x-0'}`}
      />
      <h2
        className={`kicker mb-6 ${shown ? 'animate-fade-in-up-sm' : 'opacity-0'}`}
        style={shown ? { animationDelay: `${CHAPTER_HEADING_DELAY_MS}ms` } : undefined}
      >
        {title}
      </h2>
      <div
        className={shown ? 'animate-fade-in-up' : 'opacity-0'}
        style={shown ? { animationDelay: `${CHAPTER_BODY_DELAY_MS}ms` } : undefined}
      >
        {children}
      </div>
    </div>
  );
}

function ShareBar({ report }: { report: Report }) {
  const [copied, setCopied] = useState(false);
  // Share link points at the backend /share route, which renders OG meta tags
  // for crawlers (Twitter / Slack / Discord) and then redirects humans to this
  // SPA URL. Pasting the raw SPA URL into social wouldn't produce a card
  // because the SPA shell has no per-report meta.
  const shareUrl = buildShareUrl(report.domain, report.score, report.grade, window.location.href);
  const tweet = BRAND.tweetTemplate(report.domain, report.score, report.grade, shareUrl);
  const twitterUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(tweet)}`;
  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <p className="font-display-italic text-lg text-ink-700">
        Share this report — or dare a friend.
      </p>
      <div className="flex gap-3">
        <button
          onClick={() => {
            navigator.clipboard.writeText(shareUrl);
            setCopied(true);
            setTimeout(() => setCopied(false), 1800);
          }}
          className="inline-block px-4 py-2 border border-ink-900 text-ink-900 hover:bg-ink-900 hover:text-paper text-sm font-medium font-display tracking-tightish transition-[color,background-color,border-color,transform] duration-200 active:scale-[0.98]"
        >
          {copied ? 'Copied ✓' : 'Copy link'}
        </button>
        <a
          href={twitterUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-block px-4 py-2 bg-ink-900 text-paper hover:bg-terra-deep text-sm font-medium font-display tracking-tightish transition-[color,background-color,border-color,transform] duration-200 active:scale-[0.98]"
        >
          Post on X
        </a>
      </div>
    </div>
  );
}
