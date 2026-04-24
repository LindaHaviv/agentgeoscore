import { useNavigate } from 'react-router-dom';
import { URLInput } from '../components/URLInput';
import { normalizeDomain } from '../api';

export default function HomePage() {
  const navigate = useNavigate();

  function handleSubmit(raw: string) {
    const domain = normalizeDomain(raw);
    navigate(`/report/${encodeURIComponent(domain)}`);
  }

  return (
    <section className="px-6 sm:px-10">
      <div className="max-w-4xl mx-auto pt-12 sm:pt-20 pb-10">
        <div className="kicker mb-5">a field guide · issue №1</div>
        <h1 className="font-display text-5xl sm:text-7xl text-ink-900 leading-[0.95] tracking-tightser mb-8">
          Generative Engine{' '}
          <span className="font-display-italic text-terra">Optimization,</span>
          <br className="hidden sm:block" /> graded.
        </h1>
        <p className="text-lg sm:text-xl text-ink-500 leading-relaxed max-w-2xl mb-10">
          Paste any URL. We check whether ChatGPT, Claude, Gemini, Perplexity, Groq,
          and the long tail of AI agents can{' '}
          <em className="font-display-italic text-ink-700">find</em>,{' '}
          <em className="font-display-italic text-ink-700">read</em>, and{' '}
          <em className="font-display-italic text-ink-700">cite</em> your site — then
          hand you back a grade out of one hundred, a ranked fix list, and a
          starter <code className="font-mono text-ink-700 text-base">llms.txt</code>{' '}
          you can drop straight in.
        </p>

        <URLInput onSubmit={handleSubmit} />
      </div>

      <div className="max-w-4xl mx-auto">
        <div className="rule mb-10" />
        <div className="kicker mb-8">what we measure</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-10">
          <Chapter
            num="I"
            title="Agent Access"
            desc="Are GPTBot, ClaudeBot, PerplexityBot, Google-Extended, Applebot-Extended, and the long tail of AI crawlers actually allowed in?"
          />
          <Chapter
            num="II"
            title="Discoverability"
            desc="llms.txt, sitemap.xml, HTTPS, canonical URLs — the plumbing that generative engines depend on to find the good parts."
          />
          <Chapter
            num="III"
            title="Structured Data"
            desc="schema.org JSON-LD, OpenGraph, Twitter cards — the machine-readable signals that LLMs quietly prize."
          />
          <Chapter
            num="IV"
            title="Content Clarity"
            desc="Title, meta description, a single clean H1, semantic headings, real text — not divs pretending to be a page."
          />
          <Chapter
            num="V"
            title="Citation Probe"
            desc="Live queries to Gemini, Mistral, Brave, Duck.ai, and Groq. We ask the AI: would you cite this? And then we check."
          />
          <Chapter
            num="VI"
            title="Ranked Fix List"
            desc="Every failing check becomes a prioritized fix — tagged with severity, effort, expected score lift, and a copy-pasteable snippet."
          />
        </div>

        <div className="rule mt-16 mb-6" />
        <p className="font-display-italic text-ink-400 text-center max-w-xl mx-auto">
          All probes use free-tier APIs. No data stored. The source is open.
        </p>
      </div>
    </section>
  );
}

function Chapter({ num, title, desc }: { num: string; title: string; desc: string }) {
  return (
    <div className="flex gap-5">
      <div className="font-display text-3xl text-ink-400 leading-none pt-0.5">{num}.</div>
      <div className="flex-1">
        <h3 className="font-display text-xl text-ink-900 tracking-tightish mb-1.5">{title}</h3>
        <p className="text-ink-500 leading-relaxed text-[0.95rem]">{desc}</p>
      </div>
    </div>
  );
}
