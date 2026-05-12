import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RecommendationsCard } from '../components/RecommendationsCard';

describe('RecommendationsCard', () => {
  it('renders the section header and honesty framing', () => {
    render(<RecommendationsCard />);
    expect(screen.getByText(/Off-page signals worth your time/i)).toBeInTheDocument();
    expect(screen.getByText(/we can.?t score/i)).toBeInTheDocument();
  });

  it('renders every recommendation title', () => {
    render(<RecommendationsCard />);
    for (const title of [
      /Publish original data/i,
      /Show up authentically on Reddit and GitHub/i,
      /Refresh content substantively/i,
      /Write in an authoritative, declarative tone/i,
      /Earn mentions on third-party authority sites/i,
      /experiment with \/llms\.txt/i,
    ]) {
      expect(screen.getByRole('heading', { name: title, level: 4 })).toBeInTheDocument();
    }
  });

  it('shows an evidence/source citation under each recommendation', () => {
    const { container } = render(<RecommendationsCard />);
    const items = container.querySelectorAll('li');
    expect(items.length).toBeGreaterThanOrEqual(6);
    for (const li of Array.from(items)) {
      // Last <p> in each list item is the evidence line (font-mono in source).
      const evidence = within(li as HTMLElement).getAllByText(/./)[2];
      expect(evidence).toBeTruthy();
    }
  });

  it('attributes the Princeton GEO paper at least once', () => {
    render(<RecommendationsCard />);
    expect(screen.getAllByText(/Princeton GEO/i).length).toBeGreaterThanOrEqual(2);
  });
});
