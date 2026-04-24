import { render, screen } from '@testing-library/react';
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
  it('renders the score, grade, and domain', () => {
    render(<ScoreCard report={baseReport} />);
    expect(screen.getByText('87')).toBeInTheDocument();
    expect(screen.getByText('B')).toBeInTheDocument();
    expect(screen.getByText(/grade · strong/i)).toBeInTheDocument();
    expect(screen.getByText('example.com')).toBeInTheDocument();
  });

  it('renders the duration and check count', () => {
    render(<ScoreCard report={baseReport} />);
    expect(screen.getByText(/1234 ms/)).toBeInTheDocument();
  });

  it('renders a verdict specific to the grade', () => {
    render(<ScoreCard report={{ ...baseReport, grade: 'F', score: 10 }} />);
    expect(screen.getByText(/Effectively invisible/i)).toBeInTheDocument();
    expect(screen.getByText(/grade · invisible/i)).toBeInTheDocument();
  });
});
