import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CompetitorCompareCard } from '../components/CompetitorCompareCard';
import type { CompareResponse } from '../types';

function makeRow(
  domain: string,
  overall: number,
  grade: string,
  category_scores: [number, number, number],
  error: string | null = null,
) {
  return {
    domain,
    url: error ? '' : `https://${domain}/`,
    score: overall,
    grade: grade as CompareResponse['target']['grade'],
    categories: error
      ? []
      : [
          { id: 'agent_access' as const, label: 'Agent Access', score: category_scores[0] },
          { id: 'discoverability' as const, label: 'Discoverability', score: category_scores[1] },
          { id: 'content_clarity' as const, label: 'Content Clarity', score: category_scores[2] },
        ],
    duration_ms: 100,
    error,
    cached: false,
  };
}

// Unique numbers across all cells so getByText('NN') is unambiguous in tests.
const goodResponse: CompareResponse = {
  target: makeRow('stripe.com', 92, 'A', [88, 96, 91]),
  competitors: [
    makeRow('square.com', 71, 'B', [60, 78, 73]),
    makeRow('adyen.com', 84, 'A', [82, 86, 87]),
  ],
};

describe('CompetitorCompareCard', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('disables Compare button when no competitor input is filled', () => {
    render(<CompetitorCompareCard target="stripe.com" />);
    expect(screen.getByRole('button', { name: /Compare/i })).toBeDisabled();
  });

  it('enables Compare once at least one slot has input', () => {
    render(<CompetitorCompareCard target="stripe.com" />);
    fireEvent.change(screen.getByLabelText('Competitor 1'), {
      target: { value: 'square.com' },
    });
    expect(screen.getByRole('button', { name: /Compare/i })).not.toBeDisabled();
  });

  it('renders side-by-side scores and per-competitor deltas after a successful compare', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => goodResponse,
    });

    render(<CompetitorCompareCard target="stripe.com" />);
    fireEvent.change(screen.getByLabelText('Competitor 1'), {
      target: { value: 'square.com' },
    });
    fireEvent.change(screen.getByLabelText('Competitor 2'), {
      target: { value: 'adyen.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Compare/i }));

    // Target score visible.
    expect(await screen.findByText('92')).toBeInTheDocument();
    // Competitor overall scores.
    expect(screen.getByText('71')).toBeInTheDocument();
    expect(screen.getByText('84')).toBeInTheDocument();
    // Delta text: target 92 - square 71 = +21
    expect(screen.getByText(/\(\+21\)/)).toBeInTheDocument();
    // Delta target 92 - adyen 84 = +8
    expect(screen.getByText(/\(\+8\)/)).toBeInTheDocument();
    // The honesty footer note must render.
    expect(screen.getByText(/We compare only what we score/i)).toBeInTheDocument();
  });

  it('renders an error cell for failed competitor rows without dropping the row', async () => {
    const partial: CompareResponse = {
      target: makeRow('stripe.com', 92, 'A', [88, 96, 91]),
      competitors: [
        makeRow('broken.invalid', 0, '?', [0, 0, 0], 'connection refused'),
        makeRow('adyen.com', 84, 'A', [82, 86, 87]),
      ],
    };
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => partial,
    });

    render(<CompetitorCompareCard target="stripe.com" />);
    fireEvent.change(screen.getByLabelText('Competitor 1'), {
      target: { value: 'broken.invalid' },
    });
    fireEvent.change(screen.getByLabelText('Competitor 2'), {
      target: { value: 'adyen.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Compare/i }));

    expect(await screen.findByText(/couldn't reach/i)).toBeInTheDocument();
    // The successful row is still rendered.
    expect(screen.getByText('84')).toBeInTheDocument();
  });

  it('shows the API error message when the request fails', async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'backend went sideways' }),
    });

    render(<CompetitorCompareCard target="stripe.com" />);
    fireEvent.change(screen.getByLabelText('Competitor 1'), {
      target: { value: 'square.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Compare/i }));

    await waitFor(() => {
      expect(screen.getByText(/backend went sideways/)).toBeInTheDocument();
    });
  });

  it('drops blank slots and posts only the filled competitor inputs', async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => goodResponse,
    });

    render(<CompetitorCompareCard target="stripe.com" />);
    fireEvent.change(screen.getByLabelText('Competitor 1'), {
      target: { value: 'square.com' },
    });
    // Slot 2 left blank
    fireEvent.change(screen.getByLabelText('Competitor 3'), {
      target: { value: 'adyen.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Compare/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.competitors).toEqual(['square.com', 'adyen.com']);
    expect(body.target).toBe('https://stripe.com');
  });
});
