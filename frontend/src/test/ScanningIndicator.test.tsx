import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ScanningIndicator } from '../components/ScanningIndicator';

describe('ScanningIndicator', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the URL in the headline', () => {
    render(<ScanningIndicator url="stripe.com" />);
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(/stripe\.com/);
  });

  it('renders every named scan step', () => {
    render(<ScanningIndicator url="stripe.com" />);
    for (const label of [
      'Fetching your homepage',
      'Reading robots.txt',
      'Asking Gemini if it cites you',
      'Asking Duck.ai',
      'Generating AI-search test prompts',
      'Composing the verdict',
    ]) {
      expect(screen.getByText(new RegExp(label, 'i'))).toBeInTheDocument();
    }
  });

  it('advances the active step on each interval tick', () => {
    const { container } = render(<ScanningIndicator url="stripe.com" />);
    // Initial: step 0 = "Fetching your homepage" is active (▸ marker).
    const arrows = () => Array.from(container.querySelectorAll('li')).map((li) => li.textContent || '');
    expect(arrows()[0]).toMatch(/▸\s*Fetching your homepage/);
    // After one tick (850ms) step 1 becomes active.
    act(() => {
      vi.advanceTimersByTime(900);
    });
    expect(arrows()[1]).toMatch(/▸\s*Reading robots\.txt/);
    // The completed step shows a checkmark.
    expect(arrows()[0]).toMatch(/✓/);
  });

  it('cleans up the interval on unmount', () => {
    const clearSpy = vi.spyOn(globalThis, 'clearInterval');
    const { unmount } = render(<ScanningIndicator url="stripe.com" />);
    unmount();
    expect(clearSpy).toHaveBeenCalled();
  });
});
