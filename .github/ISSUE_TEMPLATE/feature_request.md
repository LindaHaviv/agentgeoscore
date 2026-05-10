---
name: Feature request
about: Propose a new scoring gap, category, or capability
title: "[feat] "
labels: enhancement
assignees: ''
---

**What signal / capability is missing?**
e.g. "We don't currently check whether the site exposes an OpenAPI spec for AI agents to read."

**Why does it matter for GEO?**
Tie it back to the threat model: a real AI engine (ChatGPT, Claude, Gemini, Perplexity, Groq, Brave, Mistral) should treat this signal as evidence. Cite a paper, a vendor doc, or your own test if possible — see CONTRIBUTING.md for the evidence-first checklist.

**Proposed check shape**
- Inputs: HTML, robots.txt, sitemap, schema.org, etc.
- Pass / warn / fail thresholds (with rationale)
- Detail copy users would see

**Alternatives considered**
What didn't work, and why.

**Anything else?**
Mockups, API docs, related PRs.
