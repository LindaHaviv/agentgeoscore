import type { Report } from '../types';

interface Props {
  report: Report;
}

const GRADE_COLOR: Record<string, string> = {
  A: 'text-grade-a',
  B: 'text-grade-b',
  C: 'text-grade-c',
  D: 'text-grade-d',
  F: 'text-grade-f',
};

const GRADE_VERDICT: Record<string, string> = {
  A: 'AI agents will find and cite it without breaking a sweat.',
  B: 'A few tuning-up choices from best-in-class.',
  C: 'Middling. There are real gaps in how AI sees the site.',
  D: 'Poor. Most agents will struggle to read or cite it.',
  F: 'Effectively invisible to AI agents. Urgent fixes required.',
};

const GRADE_WORD: Record<string, string> = {
  A: 'Excellent',
  B: 'Strong',
  C: 'Middling',
  D: 'Weak',
  F: 'Invisible',
};

export function ScoreCard({ report }: Props) {
  const gradeColor = GRADE_COLOR[report.grade] || GRADE_COLOR.F;
  const verdict = GRADE_VERDICT[report.grade];
  const gradeWord = GRADE_WORD[report.grade];
  const totalChecks = report.categories.reduce((n, c) => n + c.checks.length, 0);

  return (
    <article className="animate-fade-in">
      <div className="kicker mb-4">a field report on</div>
      <h1 className="font-display text-4xl sm:text-5xl text-ink-900 leading-[1.05] tracking-tightser mb-6 break-all">
        {report.domain}
      </h1>

      <div className="flex items-end gap-6 sm:gap-10">
        <div className="animate-score-in">
          <div
            data-testid="score-number"
            className={`font-display text-[7.5rem] sm:text-[10rem] leading-[0.85] ${gradeColor} tracking-tightser`}
            style={{ fontVariationSettings: "'opsz' 144, 'wght' 500, 'SOFT' 30, 'WONK' 1" }}
          >
            {report.score}
          </div>
        </div>
        <div className="pb-4 sm:pb-6">
          <div
            data-testid="score-grade"
            className={`font-display-italic text-3xl sm:text-5xl ${gradeColor} leading-none mb-1`}
          >
            {report.grade}
          </div>
          <div className="kicker !text-[0.68rem]">grade · {gradeWord.toLowerCase()}</div>
        </div>
      </div>

      <div className="mt-6 rule origin-left animate-rule-draw" />

      <p className="mt-5 font-display-italic text-xl sm:text-2xl text-ink-700 leading-snug max-w-2xl">
        {verdict}
      </p>

      <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-xs font-mono text-ink-400">
        <span>
          scanned in <span className="text-ink-700">{report.duration_ms} ms</span>
        </span>
        <span className="text-ink-300">·</span>
        <span>
          <span className="text-ink-700">{report.categories.length}</span> categories
        </span>
        <span className="text-ink-300">·</span>
        <span>
          <span className="text-ink-700">{totalChecks}</span> checks
        </span>
        <span className="text-ink-300">·</span>
        <span>
          out of <span className="text-ink-700">100</span>
        </span>
      </div>
    </article>
  );
}
