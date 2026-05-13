import { useEffect, useId, useState } from 'react';
import { STAGGER_STEP_MS, staggerDelay } from '../animation';
import type { CategoryResult, CheckResult } from '../types';

const STATUS_STYLES: Record<string, { text: string; icon: string; label: string }> = {
  pass: { text: 'text-grade-a', icon: '✓', label: 'pass' },
  warn: { text: 'text-grade-c', icon: '!', label: 'warn' },
  fail: { text: 'text-grade-f', icon: '✕', label: 'fail' },
  skip: { text: 'text-ink-300', icon: '–', label: 'skip' },
};

function gradeColorForScore(score: number): string {
  if (score >= 85) return 'bg-grade-a';
  if (score >= 70) return 'bg-grade-b';
  if (score >= 55) return 'bg-grade-c';
  if (score >= 40) return 'bg-grade-d';
  return 'bg-grade-f';
}

interface Props {
  categories: CategoryResult[];
}

export function CategoryBreakdown({ categories }: Props) {
  // One mount-time rAF shared across all rows: first paint renders each bar
  // at scaleX(0), one frame later we flip to scaleX(target) so the CSS
  // transition runs. transition-delay (set per row) handles the stagger,
  // so a single state flip drives the whole cascade.
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <div>
      {categories.map((cat, i) => (
        <CategoryRow
          key={cat.id}
          category={cat}
          last={i === categories.length - 1}
          index={i}
          filled={filled}
        />
      ))}
    </div>
  );
}

function CategoryRow({
  category,
  last,
  index,
  filled,
}: {
  category: CategoryResult;
  last: boolean;
  index: number;
  filled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const score = category.score;
  const allSkipped =
    category.checks.length > 0 && category.checks.every((c) => c.status === 'skip');
  const bar = gradeColorForScore(score);
  const targetScale = (allSkipped ? 100 : score) / 100;

  return (
    <div
      className={`${last ? '' : 'border-b border-rule'} animate-fade-in-up-sm`}
      style={{ animationDelay: `${staggerDelay(index)}ms` }}
    >
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        className="w-full py-5 flex items-start gap-3 sm:gap-6 text-left group"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between gap-3 sm:gap-6 mb-3">
            <h3 className="font-display text-xl sm:text-2xl text-ink-900 tracking-tightish flex items-center flex-wrap gap-x-3 gap-y-1 min-w-0">
              <span>{category.label}</span>
              {allSkipped && (
                <span className="kicker !text-[0.6rem] !tracking-[0.18em] border border-rule px-2 py-0.5 rounded-full">
                  skipped
                </span>
              )}
            </h3>
            <div className="flex items-baseline gap-2 sm:gap-3 whitespace-nowrap shrink-0">
              {allSkipped ? (
                <span className="font-display-italic text-ink-400 text-lg">not scored</span>
              ) : (
                <>
                  <span className="font-display text-2xl sm:text-3xl text-ink-900 tabular-nums">{score}</span>
                  <span className="font-mono text-xs text-ink-400">/ 100</span>
                </>
              )}
            </div>
          </div>
          {category.summary && (
            <p className="text-ink-500 text-sm leading-relaxed mb-3 max-w-2xl">
              {category.summary}
            </p>
          )}
          <div className="flex items-center gap-4">
            <div className="flex-1 h-[3px] bg-ink-200/60 overflow-hidden rounded-full">
              <div
                className={`h-full w-full origin-left transition-transform duration-[900ms] ease-[cubic-bezier(0.22,1,0.36,1)] ${allSkipped ? 'bg-ink-200' : bar}`}
                style={{
                  transform: `scaleX(${filled ? targetScale : 0})`,
                  transitionDelay: `${staggerDelay(index, STAGGER_STEP_MS + 10)}ms`,
                  opacity: allSkipped ? 0.4 : 1,
                }}
              />
            </div>
            <span className="kicker !text-[0.6rem] whitespace-nowrap">
              {Math.round(category.weight * 100)}% of overall
            </span>
          </div>
        </div>
        <div
          className={`pt-1 w-5 text-ink-400 font-display text-2xl leading-none group-hover:text-ink-900 transition-transform duration-300 ${open ? 'rotate-45' : 'rotate-0'}`}
          aria-hidden
        >
          +
        </div>
      </button>
      {open && (
        <div
          id={panelId}
          className="pb-6 pl-0 sm:pl-6 border-l-0 sm:border-l border-rule animate-fade-in-up"
        >
          <div className="space-y-4">
            {category.checks.map((check, i) => (
              <div
                key={check.id}
                className="animate-fade-in-up-sm"
                style={{ animationDelay: `${staggerDelay(i, 50)}ms` }}
              >
                <CheckItem check={check} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CheckItem({ check }: { check: CheckResult }) {
  const style = STATUS_STYLES[check.status] || STATUS_STYLES.skip;
  return (
    <div className="flex items-start gap-4">
      <div
        className={`flex-shrink-0 w-6 h-6 flex items-center justify-center font-display text-lg ${style.text} leading-none`}
        aria-label={style.label}
      >
        {style.icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-medium text-ink-900">{check.label}</div>
        {check.detail && (
          <p className="text-ink-500 text-sm mt-1 leading-relaxed">{check.detail}</p>
        )}
      </div>
    </div>
  );
}
