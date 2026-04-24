import { useState } from 'react';
import { Link } from 'react-router-dom';
import { clearHistory, formatRelativeTime, getHistory, removeEntry } from '../history';
import type { HistoryEntry } from '../history';

const GRADE_COLOR: Record<string, string> = {
  A: 'text-grade-a border-grade-a/30',
  B: 'text-grade-b border-grade-b/30',
  C: 'text-grade-c border-grade-c/30',
  D: 'text-grade-d border-grade-d/30',
  F: 'text-grade-f border-grade-f/30',
};

const GRADE_BG: Record<string, string> = {
  A: 'bg-grade-a/8',
  B: 'bg-grade-b/8',
  C: 'bg-grade-c/8',
  D: 'bg-grade-d/8',
  F: 'bg-grade-f/8',
};

export function RecentScans() {
  const [entries, setEntries] = useState<HistoryEntry[]>(() => getHistory());

  if (entries.length === 0) return null;

  function handleClear() {
    clearHistory();
    setEntries([]);
  }

  function handleRemove(domain: string) {
    removeEntry(domain);
    setEntries(getHistory());
  }

  return (
    <div className="mt-16">
      <div className="rule mb-8" />
      <div className="flex items-baseline justify-between mb-6">
        <div className="kicker">recent scans</div>
        <button
          onClick={handleClear}
          className="text-xs text-ink-400 hover:text-ink-700 transition-colors font-mono"
        >
          clear history
        </button>
      </div>
      <div className="space-y-3">
        {entries.map((entry) => (
          <HistoryRow key={entry.domain} entry={entry} onRemove={handleRemove} />
        ))}
      </div>
    </div>
  );
}

function HistoryRow({
  entry,
  onRemove,
}: {
  entry: HistoryEntry;
  onRemove: (domain: string) => void;
}) {
  const gradeColor = GRADE_COLOR[entry.grade] || GRADE_COLOR.F;
  const gradeBg = GRADE_BG[entry.grade] || GRADE_BG.F;

  return (
    <div className="group flex items-center gap-4 py-3 px-4 -mx-4 rounded-lg hover:bg-ink-50 transition-colors">
      <Link
        to={`/report/${encodeURIComponent(entry.domain)}`}
        className="flex-1 flex items-center gap-4 min-w-0"
      >
        <div
          className={`flex-shrink-0 w-12 h-12 rounded-lg ${gradeBg} border ${gradeColor} flex items-center justify-center`}
        >
          <span className={`font-display text-xl ${gradeColor.split(' ')[0]}`}>
            {entry.grade}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-display text-lg text-ink-900 truncate">{entry.domain}</div>
          <div className="flex items-center gap-3 text-xs font-mono text-ink-400 mt-0.5">
            <span>
              <span className="text-ink-600">{entry.score}</span>/100
            </span>
            <span className="text-ink-300">·</span>
            <span>{entry.fixCount} fixes</span>
            <span className="text-ink-300">·</span>
            <span>{formatRelativeTime(entry.scannedAt)}</span>
          </div>
        </div>
      </Link>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onRemove(entry.domain);
        }}
        className="flex-shrink-0 w-6 h-6 flex items-center justify-center text-ink-300 hover:text-ink-600 opacity-0 group-hover:opacity-100 transition-opacity"
        aria-label={`Remove ${entry.domain} from history`}
      >
        ✕
      </button>
    </div>
  );
}
