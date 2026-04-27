import { useEffect, useState } from 'react';
import { fetchTestPromptsForCategory } from '../api';
import type { TestPrompt, TestPromptsBundle } from '../types';

interface Props {
  bundle: TestPromptsBundle;
  domain: string;
}

/**
 * AI-search test prompts. Each scan derives a vertical from the homepage
 * (schema.org @type, nav paths, hero copy keywords) and produces 4 prompts —
 * recommendation / use-case / comparison / persona — each with deep links
 * that pre-fill the prompt on ChatGPT, Perplexity, Claude, and Google AI Mode.
 *
 * The detected category is best-effort — the user can override it via the
 * dropdown, which calls `GET /api/test-prompts?domain=…&category=…` to
 * re-roll without re-scanning the whole site.
 */
export function TestPromptsCard({ bundle: initialBundle, domain }: Props) {
  const [bundle, setBundle] = useState<TestPromptsBundle>(initialBundle);
  const [loading, setLoading] = useState(false);
  const [overrideError, setOverrideError] = useState<string | null>(null);

  useEffect(() => {
    setBundle(initialBundle);
  }, [initialBundle]);

  async function handleCategoryChange(slug: string) {
    if (slug === bundle.detected_category.slug) return;
    setLoading(true);
    setOverrideError(null);
    try {
      const next = await fetchTestPromptsForCategory(domain, slug);
      setBundle(next);
    } catch (e) {
      setOverrideError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const conf = bundle.detected_category.confidence;
  const confLabel =
    conf === 'high' ? 'high confidence' : conf === 'medium' ? 'medium confidence' : 'low confidence — likely worth overriding';
  const confColor =
    conf === 'high'
      ? 'text-grade-a'
      : conf === 'medium'
      ? 'text-ink-700'
      : 'text-grade-d';

  return (
    <div className="paper-card p-6 sm:p-8">
      <div className="mb-5 sm:mb-6">
        <div className="kicker mb-1.5">bonus · ground-truth check</div>
        <h3 className="font-display text-2xl sm:text-3xl text-ink-900 tracking-tightish leading-tight">
          Test it yourself.
        </h3>
        <p className="text-ink-700 text-sm leading-relaxed mt-3 max-w-2xl">
          A score is only as useful as the questions you ask. Paste these into
          ChatGPT, Perplexity, Claude, or Google AI Mode and see whether{' '}
          <strong className="text-ink-900">{bundle.brand}</strong> shows up in
          the answers.
        </p>
      </div>

      <div className="bg-paper-soft/60 border border-rule p-4 mb-5 sm:mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="text-sm">
          <div className="text-ink-700">
            We think this is <strong className="text-ink-900">{bundle.detected_category.label}</strong>{' '}
            <span className={`font-mono text-xs ${confColor}`}>· {confLabel}</span>
          </div>
          {bundle.detected_category.signals.length > 0 && (
            <div
              className="text-ink-400 text-xs font-mono mt-1 truncate"
              title={bundle.detected_category.signals.join(', ')}
            >
              {bundle.detected_category.signals.slice(0, 3).join(' · ')}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <label
            htmlFor="category-override"
            className="text-xs text-ink-500 font-mono whitespace-nowrap"
          >
            Not right?
          </label>
          <select
            id="category-override"
            value={bundle.detected_category.slug}
            onChange={(e) => handleCategoryChange(e.target.value)}
            disabled={loading}
            className="text-sm border border-ink-900 px-2 py-1 bg-paper text-ink-900 font-display tracking-tightish disabled:opacity-50"
          >
            {bundle.all_categories.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {overrideError && (
        <div className="text-grade-f text-xs font-mono mb-4">
          Couldn&apos;t re-roll prompts: {overrideError}
        </div>
      )}

      <ul className="divide-y divide-rule">
        {bundle.prompts.map((p) => (
          <PromptRow key={p.angle} prompt={p} />
        ))}
      </ul>
    </div>
  );
}

function PromptRow({ prompt }: { prompt: TestPrompt }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(prompt.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <li className="py-4 sm:py-5">
      <div className="flex items-start justify-between gap-3 mb-2 flex-wrap">
        <div className="kicker text-ink-500">{prompt.label}</div>
        <button
          type="button"
          onClick={handleCopy}
          className="px-2.5 py-1 border border-ink-900 text-ink-900 hover:bg-ink-900 hover:text-paper text-[10px] font-mono uppercase tracking-wider transition-colors"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <p className="font-display text-base sm:text-lg text-ink-900 leading-snug mb-2">
        “{prompt.text}”
      </p>
      <p className="text-ink-500 text-xs leading-relaxed mb-3 italic">
        {prompt.rationale}
      </p>
      <div className="flex flex-wrap gap-2">
        <DeepLinkButton href={prompt.deep_links.chatgpt} label="ChatGPT" />
        <DeepLinkButton href={prompt.deep_links.perplexity} label="Perplexity" />
        <DeepLinkButton href={prompt.deep_links.claude} label="Claude" />
        <DeepLinkButton href={prompt.deep_links.google_ai} label="Google AI" />
      </div>
    </li>
  );
}

function DeepLinkButton({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="px-2.5 py-1 bg-ink-900 text-paper hover:bg-terra-deep text-[11px] font-display tracking-tightish transition-colors"
    >
      {label} ↗
    </a>
  );
}
