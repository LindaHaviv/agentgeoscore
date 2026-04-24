import { useState } from 'react';
import type { Fix } from '../types';

const SEVERITY_STYLES: Record<
  string,
  { mark: string; label: string; labelClass: string }
> = {
  critical: {
    mark: 'bg-grade-f',
    label: 'Critical',
    labelClass: 'text-grade-f',
  },
  important: {
    mark: 'bg-grade-c',
    label: 'Important',
    labelClass: 'text-grade-c',
  },
  minor: {
    mark: 'bg-ink-300',
    label: 'Minor',
    labelClass: 'text-ink-400',
  },
};

const EFFORT_LABEL: Record<string, string> = {
  low: 'Low effort',
  medium: 'Medium effort',
  high: 'High effort',
};

export function FixList({ items }: { items: Fix[] }) {
  if (items.length === 0) {
    return (
      <div className="paper-card p-8 text-center max-w-xl mx-auto">
        <div className="font-display-italic text-3xl text-ink-900 mb-2">Nothing to fix.</div>
        <p className="text-ink-500 leading-relaxed">
          This site is already meeting the bar for AI-agent visibility. A rare one.
        </p>
      </div>
    );
  }
  return (
    <ol className="space-y-8">
      {items.map((fix, i) => (
        <FixItem key={i} index={i} fix={fix} />
      ))}
    </ol>
  );
}

function FixItem({ fix, index }: { fix: Fix; index: number }) {
  const s = SEVERITY_STYLES[fix.severity] || SEVERITY_STYLES.minor;
  const [copied, setCopied] = useState(false);
  return (
    <li className="flex gap-5 sm:gap-7">
      <div className="flex-shrink-0 pt-1">
        <div className="font-display text-2xl text-ink-400 tabular-nums leading-none">
          {String(index + 1).padStart(2, '0')}
        </div>
      </div>
      <div className="flex-1 min-w-0 border-l border-rule pl-5 sm:pl-7">
        <div className="flex items-center gap-3 flex-wrap mb-2">
          <span className={`inline-flex items-center gap-1.5`}>
            <span className={`w-2 h-2 rounded-full ${s.mark}`} aria-hidden />
            <span className={`kicker !text-[0.65rem] ${s.labelClass}`}>{s.label}</span>
          </span>
          <span className="text-ink-300">·</span>
          <span className="kicker !text-[0.65rem] text-ink-400">
            {EFFORT_LABEL[fix.effort]}
          </span>
          {fix.score_lift > 0 && (
            <>
              <span className="text-ink-300">·</span>
              <span
                className="kicker !text-[0.65rem] text-grade-a"
                title="Estimated overall-score lift if you apply this fix"
              >
                +{fix.score_lift} pts
              </span>
            </>
          )}
        </div>
        <h3 className="font-display text-2xl text-ink-900 tracking-tightish leading-snug mb-2">
          {fix.title}
        </h3>
        {fix.detail && (
          <p className="text-ink-500 leading-relaxed max-w-prose">{fix.detail}</p>
        )}
        {fix.snippet && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-1.5">
              <span className="kicker !text-[0.6rem] text-ink-400">
                {fix.snippet_language === 'markdown'
                  ? 'drop-in llms.txt starter'
                  : fix.snippet_language === 'html'
                  ? 'drop-in html'
                  : 'drop-in snippet'}
              </span>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(fix.snippet || '');
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1600);
                }}
                className="kicker !text-[0.6rem] under-dot text-ink-500 hover:text-terra-deep"
              >
                {copied ? 'Copied ✓' : 'Copy'}
              </button>
            </div>
            <pre
              tabIndex={0}
              aria-label={`Drop-in snippet: ${fix.title}`}
              className="paper-card p-4 overflow-x-auto text-xs font-mono text-ink-700 leading-relaxed whitespace-pre focus:outline-none focus:ring-2 focus:ring-ink-900"
            >
{fix.snippet}
            </pre>
          </div>
        )}
        {fix.docs_url && (
          <div className="mt-3 text-xs">
            <a
              href={fix.docs_url}
              target="_blank"
              rel="noreferrer"
              className="under-dot text-ink-500 hover:text-terra-deep"
            >
              Read more →
            </a>
          </div>
        )}
      </div>
    </li>
  );
}
