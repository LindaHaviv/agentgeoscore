import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe('App shell', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the header wordmark on every route', () => {
    renderAt('/');
    // The home link uses its visible text "AgentGEOScore · issue №1" as the
    // accessible name (no aria-label override — would otherwise trip
    // Lighthouse's label-content-name-mismatch audit).
    // Accessible name comes from the split spans: "Agent GEO Score · issue №1".
    expect(
      screen.getByRole('link', { name: /Agent.*GEO.*Score/i }),
    ).toHaveAttribute('href', '/');
  });

  it('renders the GitHub and GEO paper nav links', () => {
    renderAt('/');
    expect(screen.getByRole('link', { name: /GEO paper/i })).toHaveAttribute(
      'href',
      expect.stringContaining('arxiv.org'),
    );
    expect(screen.getByRole('link', { name: /^GitHub$/i })).toHaveAttribute(
      'href',
      expect.stringContaining('github.com'),
    );
  });

  it('routes "/" to the HomePage', () => {
    renderAt('/');
    expect(
      screen.getByRole('heading', { name: /Generative Engine.*graded/is }),
    ).toBeInTheDocument();
  });

  it('routes "/report/:domain" to the ReportPage (loading state visible)', () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    renderAt('/report/stripe.com');
    expect(screen.getByText(/field notes · in progress/i)).toBeInTheDocument();
  });

  it('routes unknown paths to the NotFoundPage', () => {
    renderAt('/nope');
    expect(screen.getByTestId('not-found')).toBeInTheDocument();
  });

  it('renders the footer brand line', () => {
    renderAt('/');
    expect(
      screen.getByText(/An open field study of how AI agents read the web/i),
    ).toBeInTheDocument();
  });
});
