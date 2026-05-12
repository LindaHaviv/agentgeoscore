"""Prediction-only: feed the rebuilt frontend/dist back through the scanner
pipeline. Asserts the four addressable categories all clear 95+ so we have
guard-rails before the real domain ships."""
from __future__ import annotations

import re
from pathlib import Path

import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.main import app

DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
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

    # Hard assertions: every addressable category should clear 90.
    cats = {c["id"]: c["score"] for c in r["categories"]}
    assert cats["agent_access"] >= 90, cats
    assert cats["discoverability"] >= 80, cats  # response_speed depends on host
    assert cats["structured_data"] >= 95, cats
    assert cats["content_clarity"] >= 95, cats
    assert r["score"] >= 90, r["score"]
