import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import HomePage from '../pages/HomePage';

function renderHome() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route
          path="/report/:domain"
          element={<div data-testid="report-page" />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('HomePage', () => {
  it('renders the hero h1 with the graded tagline', () => {
    renderHome();
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1.textContent).toMatch(/Generative Engine/i);
    expect(h1.textContent).toMatch(/graded/i);
  });

  it('renders the "what we measure" section', () => {
    renderHome();
    expect(screen.getByText(/what we measure/i)).toBeInTheDocument();
  });

  it('renders all 6 measurement chapters', () => {
    renderHome();
    for (const title of [
      'Agent Access',
      'Discoverability',
      'Structured Data',
      'Content Clarity',
      'Citation Probe',
      'Ranked Fix List',
    ]) {
      expect(screen.getByRole('heading', { name: title, level: 3 })).toBeInTheDocument();
    }
  });

  it('submitting the URL form navigates to the encoded report route', () => {
    renderHome();
    fireEvent.change(screen.getByPlaceholderText('your-site.com'), {
      target: { value: 'STRIPE.com/payments' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Score it/i }));
    expect(screen.getByTestId('report-page')).toBeInTheDocument();
  });

  it('renders the "all probes use free-tier APIs" honesty line', () => {
    renderHome();
    expect(screen.getByText(/All probes use free-tier APIs/i)).toBeInTheDocument();
  });
});
