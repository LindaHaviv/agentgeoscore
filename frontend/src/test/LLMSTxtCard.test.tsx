import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LLMSTxtCard } from '../components/LLMSTxtCard';

const SAMPLE = `# Acme
> Acme makes widgets.

## Key pages
- [/about](/about): who we are
`;

describe('LLMSTxtCard', () => {
  it('renders the generated llms.txt content', () => {
    render(<LLMSTxtCard content={SAMPLE} domain="acme.example" />);
    expect(screen.getByText(/Your/)).toBeInTheDocument();
    expect(screen.getByText(/pre-written/i)).toBeInTheDocument();
    // The pre block contains the generated content verbatim
    expect(screen.getByText((_, el) => !!el && el.tagName === 'PRE' && el.textContent!.includes('# Acme'))).toBeTruthy();
  });

  it('renders nothing when content is empty', () => {
    const { container } = render(<LLMSTxtCard content="" domain="acme.example" />);
    expect(container.firstChild).toBeNull();
  });

  it('copies the full content when Copy is clicked', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<LLMSTxtCard content={SAMPLE} domain="acme.example" />);
    fireEvent.click(screen.getByRole('button', { name: /Copy/i }));
    expect(writeText).toHaveBeenCalledWith(SAMPLE);
  });
});
