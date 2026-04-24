import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ScoreCard } from '../components/ScoreCard';
import type { Report } from '../types';

const baseReport: Report = {
  url: 'https://example.com',
  normalized_url: 'https://example.com/',
  domain: 'example.com',
  scanned_at: new Date().toISOString(),
  duration_ms: 1234,
  score: 87,
  grade: 'B',
  categories: [
    { id: 'agent_access', label: 'Agent Access', weight: 0.25, score: 90, checks: [], summary: '' },
  ],
  fixes: [],
  suggested_llms_txt: '',
  errors: [],
};

describe('ScoreCard', () => {
  it('renders the grade and domain immediately, score animates up', async () => {
    render(<ScoreCard report={baseReport} />);
    expect(screen.getByText('B')).toBeInTheDocument();
    expect(screen.getByText(/grade · strong/i)).toBeInTheDocument();
    expect(screen.getByText('example.com')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('score-number').textContent).toBe('87');
    }, { timeout: 3000 });
  });

  it('renders the duration and check count', () => {
    render(<ScoreCard report={baseReport} />);
    expect(screen.getByText(/1234 ms/)).toBeInTheDocument();
  });

  it('renders a verdict specific to the grade', async () => {
    render(<ScoreCard report={{ ...baseReport, grade: 'F', score: 10 }} />);
    expect(screen.getByText(/Effectively invisible/i)).toBeInTheDocument();
    expect(screen.getByText(/grade · invisible/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('score-number').textContent).toBe('10');
    }, { timeout: 3000 });
  });
});
