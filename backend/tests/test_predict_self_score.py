"""Prediction-only: feed the rebuilt frontend/dist back through the scanner
pipeline. Asserts the four addressable categories all clear 95+ so we have
guard-rails before the real domain ships."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.main import app

DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# CI runs the backend pytest job in parallel with (not after) the frontend
# build, so frontend/dist/ may not exist when this file is collected. Skip
# the entire module cleanly in that case — locally the developer runs
# `npm run build` first and the assertions execute normally.
if not (DIST / "index.html").exists():
    pytest.skip(
        "frontend/dist not built — run `cd frontend && npm run build` first.",
        allow_module_level=True,
    )

INDEX = (DIST / "index.html").read_text()
ROBOTS = (DIST / "robots.txt").read_text()
SITEMAP = (DIST / "sitemap.xml").read_text()

# Must be a domain whose DNS resolves — the SSRF guard does a real lookup
# before respx can intercept. example.com is reserved for documentation
# and always resolves to public IP space.
HOST = "example.com"
BASE = f"https://{HOST}"


@respx.mock
def test_self_score_after_deploy(monkeypatch):
    # Probes off → citation_probe category excluded → only the 4 addressable categories count.
    for k in ("GEMINI_API_KEY", "MISTRAL_API_KEY", "BRAVE_API_KEY", "GROQ_API_KEY", "PAGESPEED_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DISABLE_DUCK_AI", "1")

    # Order matters in respx: specific routes BEFORE the catch-all.
    respx.get(f"{BASE}/").mock(
        return_value=Response(
            200,
            text=INDEX,
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    respx.get(f"{BASE}/robots.txt").mock(
        return_value=Response(200, text=ROBOTS, headers={"content-type": "text/plain"})
    )
    respx.get(f"{BASE}/sitemap.xml").mock(
        return_value=Response(200, text=SITEMAP, headers={"content-type": "application/xml"})
    )
    # The static shell now ships demo links like /report/stripe.com. The
    # multipage scanner samples them; in prod they resolve to the same SPA
    # shell, so simulate that by serving INDEX for every other internal path
    # on the host.
    respx.get(re.compile(rf"^https://{re.escape(HOST)}/.+$")).mock(
        return_value=Response(
            200,
            text=INDEX,
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )

    client = TestClient(app)
    resp = client.post("/api/scan", json={"url": f"{BASE}/", "include_probe": False})
    assert resp.status_code == 200
    r = resp.json()

    # Print a human-readable summary for the prediction log.
    print(f"\n=== PREDICTED OVERALL: {r['score']}/100  GRADE {r['grade']} ===")
    for c in r["categories"]:
        print(f"  {c['id']:20s} {c['score']:3d}/100  weight {c['weight']*100:.0f}%")
        for ch in c["checks"]:
            mark = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "SKIP", "error": "ERR "}.get(ch["status"], "?")
            print(f"      [{mark}] {ch['id']:35s} score={ch['score']:.2f} w={ch['weight']}")
    if r["fixes"]:
        print("\nRemaining fixes:")
        for f in r["fixes"]:
            print(f"  [{f['severity']}] {f['title']}  (+{f['score_lift']} pts)")
    else:
        print("\nNo remaining fixes — perfect score.")

    # Hard assertions: every addressable category should clear 95.
    # Actual scores on the rebuilt dist are 100/100/100/96/99, so each
    # threshold has a healthy margin while still matching the docstring's
    # "all four addressable categories clear 95+" promise.
    cats = {c["id"]: c["score"] for c in r["categories"]}
    assert cats["agent_access"] >= 95, cats
    assert cats["discoverability"] >= 95, cats
    assert cats["structured_data"] >= 95, cats
    assert cats["content_clarity"] >= 95, cats
    assert r["score"] >= 95, r["score"]
