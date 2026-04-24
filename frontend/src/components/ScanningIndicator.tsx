import { useEffect, useState } from 'react';

const STEPS = [
  'Fetching your homepage',
  'Reading robots.txt',
  'Looking for llms.txt',
  'Extracting schema.org markup',
  'Analyzing semantic HTML',
  'Asking Gemini if it cites you',
  'Asking Mistral if it cites you',
  'Checking Brave Search rankings',
  'Asking Duck.ai (GPT-4o-mini + Claude)',
  'Asking Groq compound (web search)',
  'Composing a starter llms.txt',
  'Composing the verdict',
];

export function ScanningIndicator({ url }: { url: string }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = setInterval(() => {
      setStep((s) => (s + 1) % STEPS.length);
    }, 850);
    return () => clearInterval(id);
  }, []);

  return (
    <section className="py-10 animate-fade-in">
      <div className="kicker mb-4">field notes · in progress</div>
      <h2 className="font-display text-4xl sm:text-5xl text-ink-900 tracking-tightser leading-[1.05] mb-6 break-all">
        Reading {url} carefully…
      </h2>
      <div className="rule mb-8" />

      <ol className="space-y-3 font-mono text-sm">
        {STEPS.map((label, i) => {
          const done = i < step;
          const active = i === step;
          return (
            <li
              key={label}
              className={`flex items-center gap-4 transition-colors ${
                active ? 'text-ink-900' : done ? 'text-ink-400' : 'text-ink-300'
              }`}
            >
              <span
                className={`inline-block w-5 font-display text-base leading-none ${
                  active ? 'animate-dot-pulse text-terra' : ''
                }`}
              >
                {done ? '✓' : active ? '▸' : '·'}
              </span>
              <span>
                {label}
                {active && <span className="animate-dot-pulse">…</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
