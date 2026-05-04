# Deploy — AgentGEOScore

Reference for shipping the frontend (devinapps) and backend (Fly) of AgentGEOScore, and what to double-check so a deploy doesn't silently regress share/OG behavior.

## Live URLs
- Frontend (devinapps): `https://dist-olcivbch.devinapps.com`
- Backend (Fly): `https://agentgeoscore-1ei53w.fly.dev`
- Fly app name: `agentgeoscore-1ei53w`

## Frontend — build + deploy

**`VITE_API_BASE` must be set at build time.** The frontend uses `import.meta.env.VITE_API_BASE` (see `frontend/src/api.ts`) to construct every backend call *and* every shareable link:

```ts
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';
export function buildShareUrl(domain, score, grade, fallbackUrl) {
  if (!BASE) return fallbackUrl;              // <- dead-code elim target
  return `${BASE}/share?d=${domain}&s=${score}&g=${grade}`;
}
```

If `VITE_API_BASE` is **unset** when `npm run build` runs:
1. `BASE` evaluates to a constant empty string at build time.
2. Vite/terser treats `!BASE` as always-true and deletes the entire `/share?` branch.
3. `fetch(\`${BASE}/api/scan\`)` becomes a same-origin relative request that won't reach the Fly backend from the devinapps origin.
4. "Copy link" silently copies the raw SPA `/report/<domain>` URL instead of the backend `/share?...` URL, so no OG card renders when pasted anywhere.

None of this fails CI (`vitest + tsc + build` all pass). It only manifests on a real deploy.

### Correct build command

```bash
cd frontend
VITE_API_BASE=https://agentgeoscore-1ei53w.fly.dev npm run build
```

Then deploy the `frontend/dist` directory to devinapps via the `deploy` tool (`command="frontend"`, `dir="/abs/path/to/frontend/dist"`).

### Quick post-deploy smoke check

```bash
CUR_JS=$(curl -sS https://dist-olcivbch.devinapps.com/ | grep -oE 'index-[a-zA-Z0-9_-]+\.js' | head -1)
curl -sS "https://dist-olcivbch.devinapps.com/assets/$CUR_JS" | grep -c -F '/share?'
# expect >= 1; '0' means VITE_API_BASE was missing at build time
curl -sS "https://dist-olcivbch.devinapps.com/assets/$CUR_JS" | grep -oaE 'https://[a-z0-9.-]+\.fly\.dev' | sort -u
# expect the Fly backend URL
```

## Backend — build + deploy (Fly)

Backend runs on Fly at `agentgeoscore-1ei53w`. A `fly.toml` + Dockerfile live at the **repo root** (committed in PR #23). Fly's GitHub-deploy integration auto-deploys on every merge to `main` — no manual `fly deploy` needed. Manual deploys still work via `flyctl deploy --app agentgeoscore-1ei53w` from the repo root.

### Environment variables that matter

- `FRONTEND_ORIGIN` — where `/share` redirects humans (default baked to devinapps URL). Override if the frontend moves.
- `BACKEND_ORIGIN` — optional pin for the public backend host used in `og:image` meta. If set, `/share` ignores the inbound `Host` header when composing absolute URLs. Set this on Fly to harden against Host-header spoofing:

```bash
fly secrets set --app agentgeoscore-1ei53w BACKEND_ORIGIN=https://agentgeoscore-1ei53w.fly.dev
```

- Probe keys (all optional, graceful skip when absent): `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `BRAVE_API_KEY`, `GROQ_API_KEY`. Set via `fly secrets set --app agentgeoscore-1ei53w KEY=value`.
- `PAGESPEED_API_KEY` — Google PageSpeed Insights API key for Core Web Vitals (gap #7). Same `fly secrets set` pattern.

### Fonts

The OG image renderer loads bundled fonts from `backend/app/assets/fonts/` (DejaVu Serif/Sans + Liberation Serif Italic). A font-less deploy produces PNGs < 25 KB with blank glyphs. Don't delete the fonts directory or add `fonts/` to `.gitignore`.

### Quick post-deploy smoke check

```bash
# OG PNG should be 1200x630 RGB, >25 KB
curl -sS -o /tmp/og.png 'https://agentgeoscore-1ei53w.fly.dev/api/og?d=stripe.com&s=94&g=A'
python3 -c "from PIL import Image; print(Image.open('/tmp/og.png').size)"  # -> (1200, 630)
ls -la /tmp/og.png                                                          # expect > 25 KB
# Share route should return HTML w/ OG meta + refresh redirect
curl -sS 'https://agentgeoscore-1ei53w.fly.dev/share?d=stripe.com&s=94&g=A' | grep -E 'og:image|refresh'
```

## End-to-end deploy smoke test (run after either deploy)

1. Visit `https://dist-olcivbch.devinapps.com/`, scan `stripe.com`, confirm report renders with a numeric score.
2. Scroll to ShareBar, click "Copy link".
3. Read the clipboard: `DISPLAY=:0 xclip -selection clipboard -o` — expect `https://agentgeoscore-1ei53w.fly.dev/share?d=stripe.com&s=<score>&g=<grade>`, **not** the SPA URL.
4. Paste that URL into `https://www.opengraph.xyz/url/<encoded>` and verify the card preview.
