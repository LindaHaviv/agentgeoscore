import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { scanUrl } from '../api';
import { BRAND } from '../brand';
import { CategoryBreakdown } from '../components/CategoryBreakdown';
import { FixList } from '../components/FixList';
import { LLMSTxtCard } from '../components/LLMSTxtCard';
import { ScanningIndicator } from '../components/ScanningIndicator';
import { ScoreCard } from '../components/ScoreCard';
import { URLInput } from '../components/URLInput';
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
    const url = decodeURIComponent(domain).startsWith('http')
      ? decodeURIComponent(domain)
      : `https://${decodeURIComponent(domain)}`;
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
        <div className="animate-fade-in-up">
          <ScoreCard report={report} />

          <div className="mt-16">
            <div className="rule mb-8" />
            <div className="kicker mb-6">chapter — the breakdown</div>
            <CategoryBreakdown categories={report.categories} />
          </div>

          <div className="mt-16">
            <div className="rule mb-8" />
            <div className="kicker mb-6">
              chapter — what to fix, in order
              {' '}
              <span className="text-ink-300">({report.fixes.length})</span>
            </div>
            <FixList items={report.fixes} />
          </div>

          {report.suggested_llms_txt && (
            <div className="mt-16">
              <div className="rule mb-8" />
              <div className="kicker mb-6">chapter — your drop-in llms.txt</div>
              <LLMSTxtCard content={report.suggested_llms_txt} domain={report.domain} />
            </div>
          )}

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

function ShareBar({ report }: { report: Report }) {
  const [copied, setCopied] = useState(false);
  const url = window.location.href;
  const tweet = BRAND.tweetTemplate(report.domain, report.score, report.grade, url);
  const twitterUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(tweet)}`;
  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <p className="font-display-italic text-lg text-ink-700">
        Share this report — or dare a friend.
      </p>
      <div className="flex gap-3">
        <button
          onClick={() => {
            navigator.clipboard.writeText(url);
            setCopied(true);
            setTimeout(() => setCopied(false), 1800);
          }}
          className="px-4 py-2 border border-ink-900 text-ink-900 hover:bg-ink-900 hover:text-paper text-sm font-medium font-display tracking-tightish transition-colors"
        >
          {copied ? 'Copied ✓' : 'Copy link'}
        </button>
        <a
          href={twitterUrl}
          target="_blank"
          rel="noreferrer"
          className="px-4 py-2 bg-ink-900 text-paper hover:bg-terra-deep text-sm font-medium font-display tracking-tightish transition-colors"
        >
          Post on X
        </a>
      </div>
    </div>
  );
}
