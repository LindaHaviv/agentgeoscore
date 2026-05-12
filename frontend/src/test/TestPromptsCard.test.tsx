import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TestPromptsCard } from '../components/TestPromptsCard';
import type { TestPromptsBundle } from '../types';

const bundle: TestPromptsBundle = {
  detected_category: {
    slug: 'fintech-payments',
    label: 'payments / fintech',
    persona: 'developers building checkout',
    confidence: 'medium',
    signals: ['nav link: /payments', 'keyword: payment'],
  },
  brand: 'Stripe',
  prompts: [
    {
      angle: 'category',
      label: 'Category recommendation',
      text: "What's the best payment processor for developers building checkout in 2026?",
      rationale: 'Tests whether AI engines list you among top picks for your category.',
      deep_links: {
        chatgpt: 'https://chatgpt.com/?q=test',
        perplexity: 'https://www.perplexity.ai/search?q=test',
        claude: 'https://claude.ai/new?q=test',
        google_ai: 'https://www.google.com/search?q=test&udm=50',
      },
    },
    {
      angle: 'use_case',
      label: 'Use-case discovery',
      text: 'How do I accept credit cards online?',
      rationale: 'Tests use-case discovery.',
      deep_links: {
        chatgpt: 'https://chatgpt.com/?q=u',
        perplexity: 'https://www.perplexity.ai/search?q=u',
        claude: 'https://claude.ai/new?q=u',
        google_ai: 'https://www.google.com/search?q=u&udm=50',
      },
    },
    {
      angle: 'comparison',
      label: 'Comparison',
      text: 'Stripe vs alternatives — which is best for developers building checkout?',
      rationale: 'Tests head-to-head framing.',
      deep_links: {
        chatgpt: 'https://chatgpt.com/?q=c',
        perplexity: 'https://www.perplexity.ai/search?q=c',
        claude: 'https://claude.ai/new?q=c',
        google_ai: 'https://www.google.com/search?q=c&udm=50',
      },
    },
    {
      angle: 'long_tail',
      label: 'Long-tail / persona',
      text: 'Recommend a payment processor for a SaaS founder handling subscription billing.',
      rationale: 'Tests persona-specific intent.',
      deep_links: {
        chatgpt: 'https://chatgpt.com/?q=l',
        perplexity: 'https://www.perplexity.ai/search?q=l',
        claude: 'https://claude.ai/new?q=l',
        google_ai: 'https://www.google.com/search?q=l&udm=50',
      },
    },
  ],
  all_categories: [
    { slug: 'fintech-payments', label: 'payments / fintech' },
    { slug: 'b2b-saas', label: 'B2B SaaS' },
    { slug: 'ai-tools', label: 'AI / ML tools' },
  ],
};

describe('TestPromptsCard', () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the detected category, brand, and all four prompts', () => {
    render(<TestPromptsCard bundle={bundle} domain="stripe.com" />);
    // Brand appears in the intro AND in the comparison prompt — both should render.
    expect(screen.getAllByText(/Stripe/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/payments \/ fintech/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Category recommendation/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Use-case discovery/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Comparison/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Long-tail/i).length).toBeGreaterThanOrEqual(1);
  });

  it('renders four deep-link buttons per prompt — one for each platform', () => {
    render(<TestPromptsCard bundle={bundle} domain="stripe.com" />);
    expect(screen.getAllByRole('link', { name: /ChatGPT/i })).toHaveLength(4);
    expect(screen.getAllByRole('link', { name: /Perplexity/i })).toHaveLength(4);
    expect(screen.getAllByRole('link', { name: /Claude/i })).toHaveLength(4);
    expect(screen.getAllByRole('link', { name: /Google AI/i })).toHaveLength(4);
  });

  it('deep-links open in a new tab with rel=noopener', () => {
    render(<TestPromptsCard bundle={bundle} domain="stripe.com" />);
    const link = screen.getAllByRole('link', { name: /ChatGPT/i })[0];
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link.getAttribute('href')).toMatch(/^https:\/\/chatgpt\.com\//);
  });

  it('deep-links target the documented platform endpoints', () => {
    render(<TestPromptsCard bundle={bundle} domain="stripe.com" />);
    const perplexity = screen.getAllByRole('link', { name: /Perplexity/i })[0];
    expect(perplexity.getAttribute('href')).toMatch(/perplexity\.ai/);
    const claude = screen.getAllByRole('link', { name: /Claude/i })[0];
    expect(claude.getAttribute('href')).toMatch(/claude\.ai/);
    const google = screen.getAllByRole('link', { name: /Google AI/i })[0];
    // Google AI Mode is gated by udm=50 — pin that on the rendered URL too.
    expect(google.getAttribute('href')).toMatch(/udm=50/);
  });

  it('copies the prompt text to the clipboard on Copy click', async () => {
    render(<TestPromptsCard bundle={bundle} domain="stripe.com" />);
    fireEvent.click(screen.getAllByRole('button', { name: /Copy/i })[0]);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      bundle.prompts[0].text,
    );
  });

  it('shows the override dropdown populated with all categories', () => {
    render(<TestPromptsCard bundle={bundle} domain="stripe.com" />);
    const select = screen.getByLabelText(/Not right/i) as HTMLSelectElement;
    expect(select.value).toBe('fintech-payments');
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(['fintech-payments', 'b2b-saas', 'ai-tools']);
  });

  it('re-rolls prompts via the override endpoint when the dropdown changes', async () => {
    const next: TestPromptsBundle = {
      ...bundle,
      detected_category: {
        slug: 'b2b-saas',
        label: 'B2B SaaS',
        persona: 'business teams',
        confidence: 'high',
        signals: ['user override'],
      },
      prompts: [
        {
          ...bundle.prompts[0],
          text: "What's the best SaaS tool for business teams in 2026?",
        },
        ...bundle.prompts.slice(1),
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(next),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<TestPromptsCard bundle={bundle} domain="stripe.com" />);
    fireEvent.change(screen.getByLabelText(/Not right/i), {
      target: { value: 'b2b-saas' },
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const calledUrl: string = fetchMock.mock.calls[0][0];
    expect(calledUrl).toMatch(/\/api\/test-prompts\?/);
    expect(calledUrl).toMatch(/domain=stripe\.com/);
    expect(calledUrl).toMatch(/category=b2b-saas/);

    await screen.findByText(/best SaaS tool for business teams/);
    // Detected-category text updates from "payments / fintech" to "B2B SaaS".
    expect(screen.getAllByText(/B2B SaaS/).length).toBeGreaterThanOrEqual(1);
  });

  it('surfaces an override-error banner when the re-roll fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'override exploded' }),
      }),
    );
    render(<TestPromptsCard bundle={bundle} domain="stripe.com" />);
    fireEvent.change(screen.getByLabelText(/Not right/i), {
      target: { value: 'b2b-saas' },
    });
    await waitFor(() => {
      expect(screen.getByText(/Couldn.?t re-roll prompts/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/override exploded/)).toBeInTheDocument();
  });

  it('returns early without fetching when the dropdown is set to the current slug', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<TestPromptsCard bundle={bundle} domain="stripe.com" />);
    fireEvent.change(screen.getByLabelText(/Not right/i), {
      target: { value: 'fintech-payments' },
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('surfaces a low-confidence hint to the user', () => {
    const lowConf: TestPromptsBundle = {
      ...bundle,
      detected_category: {
        ...bundle.detected_category,
        confidence: 'low',
      },
    };
    render(<TestPromptsCard bundle={lowConf} domain="stripe.com" />);
    expect(screen.getByText(/low confidence/i)).toBeInTheDocument();
  });
});
