import { Link, Route, Routes } from 'react-router-dom';
import { BRAND } from './brand';
import HomePage from './pages/HomePage';
import NotFoundPage from './pages/NotFoundPage';
import ReportPage from './pages/ReportPage';

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="px-6 sm:px-10 pt-8 pb-6">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link to="/" className="flex items-baseline gap-1 group">
            <span className="font-display text-[1.55rem] text-ink-900 leading-none">
              Agent<span className="font-display-italic text-terra">GEO</span>Score
            </span>
            <span className="font-display-italic text-ink-400 text-sm leading-none">·</span>
            <span className="kicker text-ink-400 hidden sm:inline">issue №1</span>
          </Link>
          <nav className="flex items-center gap-6 text-sm text-ink-500">
            <a
              href="https://arxiv.org/abs/2311.09735"
              target="_blank"
              rel="noreferrer"
              className="under-dot"
            >
              The GEO paper
            </a>
            <a
              href={BRAND.repoUrl}
              target="_blank"
              rel="noreferrer"
              className="hidden sm:inline under-dot"
            >
              GitHub
            </a>
          </nav>
        </div>
        <div className="max-w-6xl mx-auto mt-6 rule" />
      </header>
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/report/:domain" element={<ReportPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
      <footer className="px-6 sm:px-10 pt-8 pb-10 mt-20">
        <div className="max-w-6xl mx-auto">
          <div className="rule mb-5" />
          <nav
            aria-label="Footer"
            className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-ink-400"
          >
            <div>
              <span className="font-display text-ink-700 text-sm">{BRAND.name}</span>{' '}
              — {BRAND.tagline} An open field study of how AI agents read the web.
            </div>
            <div className="kicker !text-[0.65rem]">
              © {new Date().getFullYear()}{' '}
              <a
                href="https://github.com/LindaHaviv"
                rel="author noopener"
                target="_blank"
                className="under-dot"
              >
                Linda Vivah
              </a>{' '}
              ·{' '}
              <a
                href={`${BRAND.repoUrl}/blob/main/LICENSE`}
                rel="noopener"
                target="_blank"
                className="under-dot"
              >
                MIT
              </a>{' '}
              ·{' '}
              <a
                href={BRAND.repoUrl}
                rel="noopener"
                target="_blank"
                className="under-dot"
              >
                source
              </a>{' '}
              ·{' '}
              <a
                href={`${BRAND.repoUrl}/blob/main/SECURITY.md`}
                rel="noopener"
                target="_blank"
                className="under-dot"
              >
                security
              </a>{' '}
              ·{' '}
              <a
                href={`${BRAND.repoUrl}/blob/main/CHANGELOG.md`}
                rel="noopener"
                target="_blank"
                className="under-dot"
              >
                changelog
              </a>{' '}
              · no data stored
            </div>
          </nav>
        </div>
      </footer>
    </div>
  );
}
