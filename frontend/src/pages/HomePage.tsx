import { useNavigate } from 'react-router-dom';
import { URLInput } from '../components/URLInput';
import { normalizeDomain } from '../api';
import { staggerDelay } from '../animation';
import { useInView } from '../hooks/useInView';

export default function HomePage() {
  const navigate = useNavigate();

  function handleSubmit(raw: string) {
    const domain = normalizeDomain(raw);
    navigate(`/report/${encodeURIComponent(domain)}`);
  }

  return (
    <section className="px-6 sm:px-10">
      <div className="max-w-4xl mx-auto pt-12 sm:pt-20 pb-10">
        <div
          className="kicker mb-5 animate-fade-in-up"
          style={{ animationDelay: '0ms' }}
        >
          a field guide · issue №1
        </div>
        <h1
          className="font-display text-5xl sm:text-7xl text-ink-900 leading-[0.95] tracking-tightser mb-8 animate-fade-in-up"
          style={{ animationDelay: '80ms' }}
        >
          Generative Engine{' '}
          <span className="font-display-italic text-terra">Optimization,</span>
          <br className="hidden sm:block" /> graded.
        </h1>
        <p
          className="text-lg sm:text-xl text-ink-500 leading-relaxed max-w-2xl mb-10 animate-fade-in-up"
          style={{ animationDelay: '200ms' }}
        >
          Paste any URL. We check whether ChatGPT, Claude, Gemini, Perplexity, Groq,
          and the long tail of AI agents can{' '}
          <em className="font-display-italic text-ink-700">find</em>,{' '}
          <em className="font-display-italic text-ink-700">read</em>, and{' '}
          <em className="font-display-italic text-ink-700">cite</em> your site — then
          hand you back a grade out of one hundred, a ranked fix list, and the
          ground-truth prompts to test whether AI search actually recommends you.
        </p>

        <div
          className="animate-fade-in-up"
          style={{ animationDelay: '320ms' }}
        >
          <URLInput onSubmit={handleSubmit} />
        </div>

        <p
          className="text-sm text-ink-400 mt-4 text-center sm:text-left animate-fade-in-up"
          style={{ animationDelay: '440ms' }}
        >
          or try a known good one:{' '}
          <button
            type="button"
            onClick={() => handleSubmit('stripe.com')}
            className="under-dot text-ink-700 hover:text-terra-deep"
          >
            stripe.com
          </button>{' '}
          ·{' '}
          <button
            type="button"
            onClick={() => handleSubmit('anthropic.com')}
            className="under-dot text-ink-700 hover:text-terra-deep"
          >
            anthropic.com
          </button>{' '}
          ·{' '}
          <button
            type="button"
            onClick={() => handleSubmit('perplexity.ai')}
            className="under-dot text-ink-700 hover:text-terra-deep"
          >
            perplexity.ai
          </button>
        </p>
      </div>

      <div className="max-w-4xl mx-auto">
        <div className="rule mb-10 origin-left animate-rule-draw-fast" />
        <h2 className="kicker mb-8">what we measure</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-10">
          {CHAPTERS.map((c, i) => (
            <Chapter key={c.num} index={i} {...c} />
          ))}
        </div>

        <div className="rule mt-16 mb-6" />
        <p className="font-display-italic text-ink-400 text-center max-w-xl mx-auto">
          All probes use free-tier APIs. No data stored. The source is open.
        </p>
      </div>
    </section>
  );
}

const CHAPTERS = [
  {
    num: 'I',
    title: 'Agent Access',
    desc: 'Are GPTBot, ClaudeBot, PerplexityBot, Google-Extended, Applebot-Extended, and the long tail of AI crawlers actually allowed in?',
  },
  {
    num: 'II',
    title: 'Discoverability',
    desc: 'sitemap.xml, HTTPS, canonical URLs, response speed — the plumbing that generative engines depend on to find the good parts.',
  },
  {
    num: 'III',
    title: 'Structured Data',
    desc: 'schema.org JSON-LD, OpenGraph, Twitter cards — the machine-readable signals that LLMs quietly prize.',
  },
  {
    num: 'IV',
    title: 'Content Clarity',
    desc: 'Title, meta description, a single clean H1, semantic headings, real text — not divs pretending to be a page.',
  },
  {
    num: 'V',
    title: 'Citation Probe',
    desc: 'Live queries to Gemini, Mistral, Brave, Duck.ai, and Groq. We ask the AI: would you cite this? And then we check.',
  },
  {
    num: 'VI',
    title: 'Ranked Fix List',
    desc: 'Every failing check becomes a prioritized fix — tagged with severity, effort, expected score lift, and a copy-pasteable snippet.',
  },
];

function Chapter({
  num,
  title,
  desc,
  index,
}: {
  num: string;
  title: string;
  desc: string;
  index: number;
}) {
  const { ref, shown } = useInView<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={`flex gap-5 ${shown ? 'animate-fade-in-up-sm' : 'opacity-0'}`}
      style={shown ? { animationDelay: `${staggerDelay(index, 60)}ms` } : undefined}
    >
      <div className="font-display text-3xl text-ink-400 leading-none pt-0.5">{num}.</div>
      <div className="flex-1">
        <h3 className="font-display text-xl text-ink-900 tracking-tightish mb-1.5">{title}</h3>
        <p className="text-ink-500 leading-relaxed text-[0.95rem]">{desc}</p>
      </div>
    </div>
  );
}
