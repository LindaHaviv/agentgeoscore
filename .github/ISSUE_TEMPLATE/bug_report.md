---
name: Bug report
about: Something is wrong with a scan, the UI, or a check
title: "[bug] "
labels: bug
assignees: ''
---

**What did you scan?**
URL or `/api/scan` payload.

**What did you expect?**
e.g. "I expected `Discoverability > sitemap` to PASS because my sitemap is at /sitemap.xml"

**What happened instead?**
Paste the relevant slice of the report JSON, or attach a screenshot of the UI.

**Reproducible?**
- [ ] Yes — happens every time on this URL
- [ ] Sometimes — flaky
- [ ] Once

**Environment**
- Hosted (https://agentgeoscore.com) or self-hosted?
- Browser + OS (if a UI bug)
- Backend version: `git rev-parse HEAD` if self-hosted

**Anything else?**
Logs, network tab, related PRs, etc.

> ⚠ Security issues — do **not** file here. See [SECURITY.md](../../SECURITY.md).
