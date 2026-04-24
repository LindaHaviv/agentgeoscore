import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RadarChart } from '../components/RadarChart';
import type { CategoryResult } from '../types';

const categories: CategoryResult[] = [
  { id: 'agent_access', label: 'Agent Access', weight: 0.25, score: 90, checks: [], summary: '' },
  { id: 'discoverability', label: 'Discoverability', weight: 0.2, score: 60, checks: [], summary: '' },
  { id: 'structured_data', label: 'Structured Data', weight: 0.2, score: 75, checks: [], summary: '' },
  { id: 'content_clarity', label: 'Content Clarity', weight: 0.15, score: 80, checks: [], summary: '' },
  { id: 'citation_probe', label: 'Citation Probe', weight: 0.2, score: 50, checks: [], summary: '' },
];

describe('RadarChart', () => {
  it('renders an SVG with category scores', () => {
    render(<RadarChart categories={categories} />);
    const svg = screen.getByRole('img', { name: /radar chart/i });
    expect(svg).toBeInTheDocument();
    expect(screen.getByText('90')).toBeInTheDocument();
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.getByText('75')).toBeInTheDocument();
  });

  it('returns null for fewer than 3 categories', () => {
    const { container } = render(<RadarChart categories={categories.slice(0, 2)} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders em dash for all-skipped categories', () => {
    const skippedCat: CategoryResult[] = [
      ...categories.slice(0, 4),
      {
        id: 'citation_probe',
        label: 'Citation Probe',
        weight: 0.2,
        score: 0,
        checks: [
          { id: 'probe_1', label: 'Test', status: 'skip', score: 0, weight: 1, detail: '' },
        ],
        summary: '',
      },
    ];
    render(<RadarChart categories={skippedCat} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
