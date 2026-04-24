import { useState } from 'react';

interface Props {
  content: string;
  domain: string;
}

/**
 * A drop-in `llms.txt` starter for the scanned site.
 *
 * llms.txt (https://llmstxt.org) is the emerging standard that tells AI
 * assistants which Markdown-formatted pages best represent a site. Most sites
 * haven't published one yet — we generate one from the homepage so users can
 * copy it and drop it at `/llms.txt`.
 */
export function LLMSTxtCard({ content, domain }: Props) {
  const [copied, setCopied] = useState(false);
  if (!content) return null;

  function handleCopy() {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  function handleDownload() {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'llms.txt';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="paper-card p-6 sm:p-8">
      <div className="flex items-start justify-between gap-4 mb-3 flex-wrap">
        <div>
          <div className="kicker mb-1.5">bonus · starter file</div>
          <h3 className="font-display text-2xl sm:text-3xl text-ink-900 tracking-tightish leading-tight">
            Your <code className="font-mono text-[0.85em] text-terra-deep">llms.txt</code>, pre-written.
          </h3>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleCopy}
            className="px-3 py-1.5 border border-ink-900 text-ink-900 hover:bg-ink-900 hover:text-paper text-xs font-medium font-display tracking-tightish transition-colors"
          >
            {copied ? 'Copied ✓' : 'Copy'}
          </button>
          <button
            type="button"
            onClick={handleDownload}
            className="px-3 py-1.5 bg-ink-900 text-paper hover:bg-terra-deep text-xs font-medium font-display tracking-tightish transition-colors"
          >
            Download
          </button>
        </div>
      </div>
      <p className="text-ink-700 text-sm leading-relaxed mb-4 max-w-2xl">
        A starter <code className="font-mono text-ink-700">llms.txt</code> generated
        from {domain}'s homepage. Edit the summary + key pages, then publish at{' '}
        <code className="font-mono text-ink-700">{domain}/llms.txt</code>.
      </p>
      <pre
        tabIndex={0}
        aria-label={`Generated llms.txt for ${domain}`}
        className="bg-paper-soft/60 border border-rule p-4 overflow-x-auto text-xs font-mono text-ink-700 leading-relaxed whitespace-pre max-h-80 focus:outline-none focus:ring-2 focus:ring-ink-900"
      >
{content}
      </pre>
    </div>
  );
}
