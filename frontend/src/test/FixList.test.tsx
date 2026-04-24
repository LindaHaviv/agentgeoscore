import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FixList } from '../components/FixList';
import type { Fix } from '../types';

const fixes: Fix[] = [
  {
    severity: 'critical',
    category: 'structured_data',
    title: 'Add schema.org JSON-LD to your homepage',
    detail: 'No JSON-LD was found on the page.',
    score_lift: 8,
    effort: 'low',
    snippet: '<script type="application/ld+json">{}</script>',
    snippet_language: 'html',
    docs_url: 'https://schema.org/',
  },
  {
    severity: 'minor',
    category: 'content_clarity',
    title: 'Tighten your <title> to 10–70 characters',
    detail: 'Current title is 120 chars.',
    score_lift: 1,
    effort: 'low',
  },
];

describe('FixList', () => {
  it('renders each fix with its severity, effort, and score_lift', () => {
    render(<FixList items={fixes} />);
    expect(screen.getByText(/Add schema.org JSON-LD/)).toBeInTheDocument();
    expect(screen.getByText(/Critical/i)).toBeInTheDocument();
    expect(screen.getByText(/\+8 pts/)).toBeInTheDocument();
    expect(screen.getAllByText(/Low effort/i).length).toBeGreaterThan(0);
  });

  it('shows the empty-state for zero fixes', () => {
    render(<FixList items={[]} />);
    expect(screen.getByText(/Nothing to fix/i)).toBeInTheDocument();
  });

  it('copies the snippet to clipboard when the Copy button is clicked', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<FixList items={fixes} />);
    fireEvent.click(screen.getAllByRole('button', { name: /Copy/ })[0]);
    expect(writeText).toHaveBeenCalledWith(
      '<script type="application/ld+json">{}</script>'
    );
  });
});
