/**
 * Side-by-side competitor compare. Up to 3 competitor domains run through
 * the same scan pipeline as the target, results render as columns alongside
 * the target's own score. Per-category deltas are computed locally.
 *
 * The honesty framing is important: "this only compares signals we score —
 * it doesn't capture inbound links, brand authority, or content depth
 * beyond the homepage + sampled pages." See the footer note below.
 */
import { useState } from 'react';
import { compareCompetitors } from '../api';
import type { CategoryId, CompareResponse, CompareSummary } from '../types';

interface Props {
  /** Target domain — typically the report's `report.domain`. */
  target: string;
}

const SLOTS = 3;

function gradeColorForScore(score: number): string {
  if (score >= 85) return 'text-grade-a';
  if (score >= 70) return 'text-grade-b';
  if (score >= 55) return 'text-grade-c';
  if (score >= 40) return 'text-grade-d';
  return 'text-grade-f';
}

function deltaFor(targetScore: number, competitorScore: number): number {
  return targetScore - competitorScore;
}

function formatDelta(d: number): string {
  if (d === 0) return '±0';
  return d > 0 ? `+${d}` : `${d}`;
}

function deltaTone(d: number): string {
  if (d > 4) return 'text-grade-a';
  if (d < -4) return 'text-grade-f';
  return 'text-ink-400';
}

export function CompetitorCompareCard({ target }: Props) {
  const [inputs, setInputs] = useState<string[]>(['', '', '']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompareResponse | null>(null);

  const filled = inputs.map((s) => s.trim()).filter(Boolean);
  const canSubmit = filled.length > 0 && !loading;

  function updateSlot(i: number, value: string) {
    setInputs((prev) => prev.map((v, j) => (j === i ? value : v)));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    try {
      const data = await compareCompetitors(target, filled);
      setResult(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to compare';
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="paper-card p-6 sm:p-8">
      <div className="kicker mb-2">competitor baseline</div>
      <h3 className="font-display text-2xl text-ink-900 mb-3">
        How does {target} stack up against your competitors?
      </h3>
      <p className="text-ink-500 text-sm leading-relaxed mb-6 max-w-2xl">
        Drop in 1–3 competitor domains and we'll run the same scan pipeline against
        each one. Results are cached for an hour so re-running with the same
        competitors is instant.
      </p>

      <form onSubmit={onSubmit} className="flex flex-col sm:flex-row gap-3 mb-2">
        {Array.from({ length: SLOTS }).map((_, i) => (
          <input
            key={i}
            type="text"
            inputMode="url"
            value={inputs[i]}
            onChange={(e) => updateSlot(i, e.target.value)}
            placeholder={i === 0 ? 'competitor.com' : 'optional'}
            disabled={loading}
            className="flex-1 px-4 py-3 bg-paper border border-rule rounded font-mono text-sm text-ink-900 placeholder-ink-300 focus:outline-none focus:border-ink-700 disabled:opacity-50"
            aria-label={`Competitor ${i + 1}`}
          />
        ))}
        <button
          type="submit"
          disabled={!canSubmit}
          className="px-6 py-3 bg-ink-900 text-paper rounded font-display text-sm tracking-wide hover:bg-terra-deep transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {loading ? 'Comparing…' : 'Compare'}
        </button>
      </form>
      <p className="text-ink-400 text-xs mb-6">
        Citation probes are off for compare runs (would otherwise add 5–15 s per
        competitor). Re-run a single domain via the report search bar to see probes.
      </p>

      {error && (
        <div className="border-l-2 border-grade-f pl-4 py-2 mb-4 text-sm">
          <span className="text-grade-f font-mono">error:</span>{' '}
          <span className="text-ink-500">{error}</span>
        </div>
      )}

      {result && <CompareResultsTable result={result} />}
    </div>
  );
}

function CompareResultsTable({ result }: { result: CompareResponse }) {
  const allRows: CompareSummary[] = [result.target, ...result.competitors];
  // Per-category labels — pull from whichever row has the most categories
  // (a fully-failed row carries no categories).
  const categoryRows = result.target.categories.length
    ? result.target.categories
    : result.competitors.find((c) => c.categories.length)?.categories ?? [];

  return (
    <div className="mt-2">
      <div className="rule mb-4" />
      <div className="overflow-x-auto -mx-2">
        <div className="px-2 inline-block min-w-full align-top">
          <div className="grid gap-x-4 gap-y-2"
            style={{ gridTemplateColumns: `minmax(140px, max-content) repeat(${allRows.length}, minmax(110px, 1fr))` }}
          >
            {/* Header row: empty corner + each domain */}
            <div />
            {allRows.map((row, i) => (
              <div key={`h-${row.domain}`} className="text-left">
                <div className="kicker !text-[0.6rem] mb-1">
                  {i === 0 ? 'your site' : `competitor ${i}`}
                </div>
                <div className="font-mono text-xs text-ink-700 truncate" title={row.domain}>
                  {row.domain}
                </div>
                {row.cached && (
                  <div className="text-[0.6rem] text-ink-300 font-mono mt-0.5">cached</div>
                )}
              </div>
            ))}

            {/* Overall score row */}
            <div className="font-display text-sm text-ink-900 self-center">Overall</div>
            {allRows.map((row) => (
              <div key={`s-${row.domain}`} className="self-center">
                {row.error ? (
                  <ErrorCell error={row.error} />
                ) : (
                  <ScoreCell row={row} target={result.target} />
                )}
              </div>
            ))}

            {/* Per-category rows */}
            {categoryRows.map((cat) => (
              <CategoryRow
                key={cat.id}
                catId={cat.id}
                catLabel={cat.label}
                rows={allRows}
                target={result.target}
              />
            ))}
          </div>
        </div>
      </div>

      <p className="text-ink-400 text-xs mt-6 leading-relaxed">
        We compare only what we score. Inbound link authority, brand strength,
        ad spend, and content depth beyond the homepage + sampled pages aren't
        captured here. Treat this as a directional signal, not a final verdict.
      </p>
    </div>
  );
}

function CategoryRow({
  catId,
  catLabel,
  rows,
  target,
}: {
  catId: CategoryId;
  catLabel: string;
  rows: CompareSummary[];
  target: CompareSummary;
}) {
  return (
    <>
      <div className="text-ink-700 text-sm self-center pt-1 border-t border-rule">
        {catLabel}
      </div>
      {rows.map((row) => {
        const cat = row.categories.find((c) => c.id === catId);
        return (
          <div key={`${catId}-${row.domain}`} className="self-center pt-1 border-t border-rule">
            {row.error ? (
              <span className="text-ink-300 font-mono text-xs">—</span>
            ) : !cat ? (
              <span className="text-ink-300 font-mono text-xs">n/a</span>
            ) : (
              <CategoryCell
                score={cat.score}
                isTarget={row.domain === target.domain}
                targetScore={
                  target.categories.find((c) => c.id === catId)?.score ?? cat.score
                }
              />
            )}
          </div>
        );
      })}
    </>
  );
}

function ScoreCell({
  row,
  target,
}: {
  row: CompareSummary;
  target: CompareSummary;
}) {
  const isTarget = row.domain === target.domain;
  const d = deltaFor(target.score, row.score);
  return (
    <div className="flex items-baseline gap-2">
      <span className={`font-display text-2xl ${gradeColorForScore(row.score)}`}>
        {row.score}
      </span>
      <span className="font-mono text-[0.65rem] text-ink-400 uppercase">{row.grade}</span>
      {!isTarget && (
        <span
          className={`font-mono text-xs ${deltaTone(d)}`}
          title={`Your site is ${formatDelta(d)} vs ${row.domain}`}
        >
          ({formatDelta(d)})
        </span>
      )}
    </div>
  );
}

function CategoryCell({
  score,
  isTarget,
  targetScore,
}: {
  score: number;
  isTarget: boolean;
  targetScore: number;
}) {
  const d = deltaFor(targetScore, score);
  return (
    <div className="flex items-baseline gap-2">
      <span className={`font-mono text-base ${gradeColorForScore(score)}`}>{score}</span>
      {!isTarget && (
        <span className={`font-mono text-xs ${deltaTone(d)}`}>{formatDelta(d)}</span>
      )}
    </div>
  );
}

function ErrorCell({ error }: { error: string }) {
  return (
    <div className="text-grade-f text-xs font-mono leading-snug" title={error}>
      couldn't reach
    </div>
  );
}
