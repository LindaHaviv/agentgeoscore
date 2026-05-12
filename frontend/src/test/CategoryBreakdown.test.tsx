import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CategoryBreakdown } from '../components/CategoryBreakdown';
import type { CategoryResult, CheckResult } from '../types';

function check(
  id: string,
  status: CheckResult['status'],
  detail = '',
): CheckResult {
  return { id, label: id.replace(/_/g, ' '), status, score: 1, weight: 1, detail };
}

const categories: CategoryResult[] = [
  {
    id: 'agent_access',
    label: 'Agent Access',
    weight: 0.25,
    score: 95,
    summary: 'AI crawlers are welcomed.',
    checks: [
      check('robots_exists', 'pass', 'robots.txt present'),
      check('core_ai_bots', 'pass', 'all major bots allowed'),
      check('broad_ai_bots', 'warn', 'cohere-ai missing'),
    ],
  },
  {
    id: 'citation_probe',
    label: 'Citation Probe',
    weight: 0.2,
    score: 0,
    summary: '',
    checks: [
      check('probe_gemini', 'skip'),
      check('probe_mistral', 'skip'),
    ],
  },
];

describe('CategoryBreakdown', () => {
  it('renders one row per category with the score, label, and weight', () => {
    render(<CategoryBreakdown categories={categories} />);
    expect(screen.getByText('Agent Access')).toBeInTheDocument();
    expect(screen.getByText('95')).toBeInTheDocument();
    expect(screen.getByText(/25% of overall/i)).toBeInTheDocument();
    expect(screen.getByText('Citation Probe')).toBeInTheDocument();
    expect(screen.getByText(/20% of overall/i)).toBeInTheDocument();
  });

  it('badges all-skipped categories as "not scored" / "skipped" instead of showing a 0', () => {
    render(<CategoryBreakdown categories={categories} />);
    expect(screen.getByText(/not scored/i)).toBeInTheDocument();
    expect(screen.getByText(/^skipped$/i)).toBeInTheDocument();
  });

  it('renders the category summary line when present', () => {
    render(<CategoryBreakdown categories={categories} />);
    expect(screen.getByText(/AI crawlers are welcomed/i)).toBeInTheDocument();
  });

  it('hides per-check rows by default and shows them after clicking the row', () => {
    render(<CategoryBreakdown categories={categories} />);
    expect(screen.queryByText('robots exists')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Agent Access/i }));
    expect(screen.getByText('robots exists')).toBeInTheDocument();
    expect(screen.getByText(/robots\.txt present/)).toBeInTheDocument();
    expect(screen.getByText(/cohere-ai missing/)).toBeInTheDocument();
  });

  it('renders pass / warn / fail / skip icons with accessible labels', () => {
    const cats: CategoryResult[] = [
      {
        ...categories[0],
        checks: [
          check('p', 'pass'),
          check('w', 'warn'),
          check('f', 'fail'),
          check('s', 'skip'),
        ],
      },
    ];
    render(<CategoryBreakdown categories={cats} />);
    fireEvent.click(screen.getByRole('button', { name: /Agent Access/i }));
    expect(screen.getByLabelText('pass')).toBeInTheDocument();
    expect(screen.getByLabelText('warn')).toBeInTheDocument();
    expect(screen.getByLabelText('fail')).toBeInTheDocument();
    expect(screen.getByLabelText('skip')).toBeInTheDocument();
  });

  it('renders nothing inside the container when no categories are passed', () => {
    const { container } = render(<CategoryBreakdown categories={[]} />);
    expect(container.firstChild?.childNodes.length).toBe(0);
  });

  it('uses the correct grade-color bar across all score bands', () => {
    const bands: Array<[number, string]> = [
      [95, 'bg-grade-a'],
      [80, 'bg-grade-b'],
      [60, 'bg-grade-c'],
      [50, 'bg-grade-d'],
      [10, 'bg-grade-f'],
    ];
    for (const [score, klass] of bands) {
      const { container, unmount } = render(
        <CategoryBreakdown
          categories={[
            {
              id: 'agent_access',
              label: `Score ${score}`,
              weight: 0.25,
              score,
              summary: '',
              checks: [check('p', 'pass')],
            },
          ]}
        />,
      );
      const bar = container.querySelector(`.${klass}`);
      expect(bar, `score=${score} should produce ${klass}`).not.toBeNull();
      unmount();
    }
  });

  it('falls back to the skip style on an unknown status string', () => {
    const cats: CategoryResult[] = [
      {
        ...categories[0],
        checks: [
          // Cast through unknown — covers the `STATUS_STYLES[check.status] || STATUS_STYLES.skip` fallback.
          { ...check('x', 'pass'), status: 'mystery' as unknown as CheckResult['status'] },
        ],
      },
    ];
    render(<CategoryBreakdown categories={cats} />);
    fireEvent.click(screen.getByRole('button', { name: /Agent Access/i }));
    // Skip icon is the en-dash; check that it renders without throwing.
    expect(screen.getByLabelText('skip')).toBeInTheDocument();
  });
});
