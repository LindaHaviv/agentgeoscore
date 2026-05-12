import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import NotFoundPage from '../pages/NotFoundPage';

function renderRouted() {
  return render(
    <MemoryRouter>
      <NotFoundPage />
    </MemoryRouter>,
  );
}

describe('NotFoundPage', () => {
  it('renders the editorial 404 heading', () => {
    renderRouted();
    expect(
      screen.getByRole('heading', { name: /isn.?t in the field guide/i }),
    ).toBeInTheDocument();
  });

  it('renders the "chapter missing" kicker', () => {
    renderRouted();
    expect(screen.getByText(/chapter missing/i)).toBeInTheDocument();
  });

  it('renders a back-home link pointing at "/"', () => {
    renderRouted();
    const link = screen.getByRole('link', { name: /back to the homepage/i });
    expect(link).toHaveAttribute('href', '/');
  });

  it('flags the page with a data-testid for e2e selection', () => {
    const { container } = renderRouted();
    expect(container.querySelector('[data-testid="not-found"]')).not.toBeNull();
  });
});
