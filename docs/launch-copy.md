# Launch copy — drafts for the public OSS release

Honest, sometimes-self-deprecating drafts. Lift any of these as-is or
remix. Live link: https://dist-olcivbch.devinapps.com/. Repo:
https://github.com/LindaHaviv/agentgeoscore.

---

## GitHub repo metadata

**Description (160-char max):**
> Score any URL for how AI agents find, read, and cite it. 8 evidence-backed gap scanners + 5 live LLM citation probes + ranked fix list.

**Topics (paste into the "Topics" field on the repo page or via `gh repo edit`):**
```
geo
generative-engine-optimization
seo
llm
ai-agents
ai-search
fastapi
react
python
typescript
playwright
```

**Homepage URL field:**
```
https://dist-olcivbch.devinapps.com/
```

**One-shot CLI to set them all (you run this; I don't have a token with `repo:write` from here):**

```bash
gh repo edit LindaHaviv/agentgeoscore \
  --description "Score any URL for how AI agents find, read, and cite it. 8 evidence-backed gap scanners + 5 live LLM citation probes + ranked fix list." \
  --homepage "https://dist-olcivbch.devinapps.com/" \
  --add-topic geo \
  --add-topic generative-engine-optimization \
  --add-topic seo \
  --add-topic llm \
  --add-topic ai-agents \
  --add-topic ai-search \
  --add-topic fastapi \
  --add-topic react \
  --add-topic python \
  --add-topic typescript \
  --add-topic playwright
```

---

## Show HN

**Title (Show HN posts have to start with `Show HN:`):**
> Show HN: AgentGEOScore – grade any URL on how AI agents find and cite it

**Body:**
> Hi HN — I built this because traditional SEO tools score for Google's
> ranking algorithm, not for whether ChatGPT, Claude, Gemini, Perplexity,
> or Brave actually cite your site when someone asks them a question.
> Those are different problems and the second one is becoming the more
> important one.
>
> Paste a URL, get back:
>
> - A 0–100 GEO score across 5 weighted categories (40 individual
>   checks). Methodology is grounded in the Princeton GEO paper
>   (arxiv:2311.09735) and a few platform docs (OpenAI / Anthropic /
>   Perplexity bot policies).
> - A ranked, copy-pasteable fix list — each fix has a severity, an
>   effort estimate, an expected score lift, and ready-to-paste HTML.
> - Live citation probes: I actually query Brave, Gemini, Groq, and
>   Duck.ai with category-specific prompts derived from the page's
>   schema + content, and report back whether your site shows up.
> - 4 AI-search test prompts you can paste into ChatGPT / Perplexity /
>   Claude / Google AI Mode, with deep-link buttons.
>
> What it deliberately doesn't do: track scores over time, store any
> data, gate behind a login, or pretend to be authoritative about
> exactly how each engine ranks. The score is a heuristic informed by
> public research; the citation probes are the ground truth.
>
> Stack is FastAPI + Vite/React, deployed on Fly.io. Everything is
> open source under MIT. The repo includes a SECURITY.md (the backend
> fetches arbitrary user-supplied URLs, so it ships with an SSRF guard,
> per-IP rate limits, strict CSP, and the rest of the usual hardening).
>
> Live demo: https://dist-olcivbch.devinapps.com/
> Repo: https://github.com/LindaHaviv/agentgeoscore
>
> Curious to hear which of the 8 "gap scanners" feels most useful or
> off-base, and what other GEO signals you'd want next. The category
> lexicon is hand-curated from ~200 homepages and is the easiest place
> to contribute — PRs welcome.

---

## X / Twitter thread (5 posts)

**1/ (hook)**
> Just open-sourced AgentGEOScore.
>
> Paste any URL → get a 0–100 score for how well AI agents (ChatGPT,
> Claude, Gemini, Perplexity, Groq, Brave) can find, read, and cite it.
>
> Live: https://dist-olcivbch.devinapps.com/
> Repo: https://github.com/LindaHaviv/agentgeoscore

**2/ (what's different)**
> Traditional SEO tools score for Google's ranking. AgentGEOScore
> scores for AI citation. They're different.
>
> 5 weighted categories. 40 evidence-backed checks. Methodology rooted
> in the Princeton GEO paper + the public bot policies of every major
> AI engine.

**3/ (citation probes)**
> The score is a heuristic. The citation probes are the ground truth.
>
> Each scan actually queries Brave / Gemini / Groq / Duck.ai with
> prompts derived from your page and tells you whether you show up.
>
> Plus 4 deep-linkable test prompts for ChatGPT / Perplexity / Claude /
> Google AI Mode so you can verify by hand.

**4/ (fixes)**
> Every score comes with a ranked fix list — severity, effort,
> expected lift, and copy-pasteable HTML.
>
> e.g. *"Add explicit AI-bot rules to robots.txt"* with a ready-made
> snippet that allows GPTBot / ClaudeBot / PerplexityBot / Google-Extended
> / Applebot-Extended explicitly. No more relying on wildcards.

**5/ (call to action)**
> MIT-licensed. FastAPI + React. SECURITY.md, hardening notes,
> contributing guide all in the repo.
>
> The category lexicon is hand-curated and the easiest place to
> contribute — if your industry isn't covered, send a PR with a
> CategoryDef + detection test.
>
> Live: https://dist-olcivbch.devinapps.com/
> Repo: https://github.com/LindaHaviv/agentgeoscore

---

## LinkedIn post

> I just open-sourced AgentGEOScore — a public-domain audit tool for
> Generative Engine Optimization (GEO).
>
> Why GEO and not SEO? Because the audience reading your site has
> changed. ChatGPT, Claude, Gemini, Perplexity, and Brave are now an
> intermediation layer between your content and your readers. They
> have their own crawlers, their own ranking signals, and their own
> rules about which sites they're willing to cite. Most of those
> signals don't overlap with the ones Google has trained us to optimize
> for.
>
> AgentGEOScore grades any URL on 40 evidence-backed checks across
> five categories — Agent Access, Discoverability, Structured Data,
> Content Clarity, and live Citation Probes against multiple AI engines.
> It returns a 0–100 score, a letter grade, and a ranked fix list with
> copy-pasteable HTML for each recommendation. The methodology is
> rooted in the Princeton GEO paper (Aggarwal et al., 2024) and the
> public bot policies of every major AI engine.
>
> Free to use, no signup required, MIT-licensed. Contributions welcome
> — the category lexicon is hand-curated and the easiest place to
> start.
>
> Demo: https://dist-olcivbch.devinapps.com/
> Repo: https://github.com/LindaHaviv/agentgeoscore

---

## README hero block (drop into the very top of README.md)

```markdown
# AgentGEOScore

> Score any URL on how well AI agents — ChatGPT, Claude, Gemini,
> Perplexity, Groq, Brave — can **find**, **read**, and **cite** it.

[Live demo](https://dist-olcivbch.devinapps.com/) · [The GEO paper](https://arxiv.org/abs/2311.09735) · [Hardening](#hardening) · [Contributing](#contributing)

![AgentGEOScore report breakdown — 80/B for stripe.com showing all 5 categories](docs/hero-breakdown.png)

A 0–100 score across 40 evidence-backed checks, a ranked fix list with
copy-pasteable HTML for each recommendation, and live citation probes
against multiple AI engines. Free, no signup, MIT-licensed.
```

---

## Press kit one-pager

**Project:** AgentGEOScore
**Tagline:** Generative Engine Optimization, graded.
**Author:** Linda Haviv (linda.haviv@gmail.com)
**License:** MIT
**Stack:** FastAPI · Python 3.11 · React · Vite · Tailwind · Pillow · Playwright
**Live:** https://dist-olcivbch.devinapps.com/
**Repo:** https://github.com/LindaHaviv/agentgeoscore
**What it does:** Grades any URL (0–100, A–F) on how well AI agents find, read, and cite it. 5 categories, 40 checks, 8 evidence-backed gap scanners, 5 live LLM citation probes, ranked fix list with copy-pasteable HTML.
**What it doesn't do:** Track over time, store data, require login, claim to know exactly how each engine ranks.
**Origin:** Built to address the gap between traditional SEO tooling (optimized for Google's ranking) and the new reality (AI engines as the dominant intermediation layer).
**Methodology:** Princeton GEO paper (Aggarwal et al., 2024) + public bot/crawler policies from OpenAI, Anthropic, Google, Perplexity, Brave, and Mistral.
**Privacy:** No persistence, no cookies, no third-party tracking. Probe API keys never leave the backend.
**Hardening:** SSRF guard with per-redirect IP validation, per-IP rate limits, strict CSP, HSTS, vulnerability disclosure policy.
