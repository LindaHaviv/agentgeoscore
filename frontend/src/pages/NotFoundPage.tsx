import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <section
      data-testid="not-found"
      className="px-6 sm:px-10 py-20 max-w-2xl mx-auto text-center"
    >
      <div className="kicker text-grade-f mb-3">chapter missing</div>
      <h1 className="font-display text-5xl sm:text-6xl text-ink-900 leading-[0.95] tracking-tightser mb-5">
        This page isn't in the field guide.
      </h1>
      <p className="font-display-italic text-lg text-ink-500 mb-10">
        The URL you followed doesn't match any route in this issue.
      </p>
      <Link
        to="/"
        className="inline-block px-6 py-3 bg-ink-900 text-paper font-display tracking-tightish text-sm hover:bg-terra-deep transition-colors"
      >
        Back to the homepage
      </Link>
    </section>
  );
}
