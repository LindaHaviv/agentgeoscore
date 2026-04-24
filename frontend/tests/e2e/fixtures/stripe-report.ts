import type { Report } from "../../../src/types";

export const stripeReport: Report = {
  "url": "https://stripe.com/",
  "normalized_url": "https://stripe.com/",
  "domain": "stripe.com",
  "scanned_at": "2026-04-23T18:04:51.491205Z",
  "duration_ms": 1189,
  "score": 94,
  "grade": "A",
  "categories": [
    {
      "id": "agent_access",
      "label": "Agent Access",
      "weight": 0.25,
      "score": 95,
      "checks": [
        {
          "id": "robots_exists",
          "label": "robots.txt reachable",
          "status": "pass",
          "score": 1.0,
          "weight": 0.5,
          "detail": "robots.txt served at https://stripe.com/robots.txt",
          "evidence": null
        },
        {
          "id": "core_ai_bots",
          "label": "Core AI crawlers allowed",
          "status": "pass",
          "score": 1.0,
          "weight": 3.0,
          "detail": "All core AI crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, Applebot-Extended) are allowed.",
          "evidence": {
            "blocked": [],
            "core_set": [
              "Applebot-Extended",
              "ChatGPT-User",
              "ClaudeBot",
              "GPTBot",
              "Google-Extended",
              "OAI-SearchBot",
              "PerplexityBot"
            ]
          }
        },
        {
          "id": "broad_ai_bots",
          "label": "Long-tail AI crawlers allowed",
          "status": "pass",
          "score": 1.0,
          "weight": 1.0,
          "detail": "No additional AI bots are blocked beyond the core set.",
          "evidence": {
            "blocked": [],
            "allowed": [
              "GPTBot",
              "ChatGPT-User",
              "OAI-SearchBot",
              "ClaudeBot",
              "Claude-Web",
              "PerplexityBot",
              "Perplexity-User",
              "Google-Extended",
              "GoogleOther",
              "Bytespider",
              "Applebot-Extended",
              "Amazonbot",
              "cohere-ai",
              "Meta-ExternalAgent",
              "DuckAssistBot",
              "YouBot",
              "FacebookBot"
            ]
          }
        },
        {
          "id": "explicit_ai_rules",
          "label": "Explicit AI-bot rules in robots.txt",
          "status": "warn",
          "score": 0.5,
          "weight": 0.5,
          "detail": "No named AI bots in robots.txt \u2014 you're relying on wildcard defaults. Add explicit `User-agent: GPTBot` etc. entries to make intent clear.",
          "evidence": null
        }
      ],
      "summary": ""
    },
    {
      "id": "discoverability",
      "label": "Discoverability",
      "weight": 0.2,
      "score": 95,
      "checks": [
        {
          "id": "llms_txt",
          "label": "llms.txt present",
          "status": "pass",
          "score": 1.0,
          "weight": 2.0,
          "detail": "Found llms.txt (63917 bytes).",
          "evidence": null
        },
        {
          "id": "llms_full_txt",
          "label": "llms-full.txt present",
          "status": "warn",
          "score": 0.3,
          "weight": 0.5,
          "detail": "Optional: add /llms-full.txt with full-content Markdown for richer AI grounding.",
          "evidence": null
        },
        {
          "id": "sitemap",
          "label": "Sitemap available",
          "status": "pass",
          "score": 1.0,
          "weight": 1.5,
          "detail": "sitemap.xml found (declared in robots.txt).",
          "evidence": null
        },
        {
          "id": "https",
          "label": "HTTPS enabled",
          "status": "pass",
          "score": 1.0,
          "weight": 1.5,
          "detail": "Site served over HTTPS.",
          "evidence": null
        },
        {
          "id": "canonical",
          "label": "Canonical URL declared",
          "status": "pass",
          "score": 1.0,
          "weight": 0.8,
          "detail": "Homepage declares a canonical URL.",
          "evidence": null
        },
        {
          "id": "response_speed",
          "label": "Homepage response speed",
          "status": "pass",
          "score": 1.0,
          "weight": 0.7,
          "detail": "Fast response (226 ms).",
          "evidence": null
        }
      ],
      "summary": ""
    },
    {
      "id": "structured_data",
      "label": "Structured Data",
      "weight": 0.2,
      "score": 100,
      "checks": [
        {
          "id": "jsonld_present",
          "label": "schema.org JSON-LD present",
          "status": "pass",
          "score": 1.0,
          "weight": 3.0,
          "detail": "Found 2 JSON-LD block(s): Organization, WebSite.",
          "evidence": {
            "types": [
              "Organization",
              "WebSite"
            ],
            "count": 2
          }
        },
        {
          "id": "jsonld_rich",
          "label": "Rich schema.org types used",
          "status": "pass",
          "score": 1.0,
          "weight": 1.5,
          "detail": "Rich types detected: Organization, WebSite.",
          "evidence": null
        },
        {
          "id": "opengraph",
          "label": "OpenGraph tags present",
          "status": "pass",
          "score": 1.0,
          "weight": 2.0,
          "detail": "All core OpenGraph tags present.",
          "evidence": {
            "present": [
              "og:description",
              "og:image",
              "og:title",
              "og:type",
              "og:url"
            ]
          }
        },
        {
          "id": "twitter_card",
          "label": "Twitter/X card tags",
          "status": "pass",
          "score": 1.0,
          "weight": 0.8,
          "detail": "twitter:card = summary_large_image.",
          "evidence": null
        }
      ],
      "summary": ""
    },
    {
      "id": "content_clarity",
      "label": "Content Clarity",
      "weight": 0.15,
      "score": 82,
      "checks": [
        {
          "id": "title_quality",
          "label": "<title> quality",
          "status": "pass",
          "score": 1.0,
          "weight": 1.5,
          "detail": "Title: \"Stripe | Financial Infrastructure to Grow Your Revenue\" (54 chars).",
          "evidence": null
        },
        {
          "id": "meta_description",
          "label": "Meta description",
          "status": "pass",
          "score": 1.0,
          "weight": 1.2,
          "detail": "Description: 149 chars.",
          "evidence": null
        },
        {
          "id": "h1_single",
          "label": "Exactly one H1",
          "status": "warn",
          "score": 0.5,
          "weight": 1.0,
          "detail": "2 H1 tags \u2014 ideally just one.",
          "evidence": null
        },
        {
          "id": "semantic_html",
          "label": "Semantic HTML landmarks",
          "status": "pass",
          "score": 1.0,
          "weight": 1.5,
          "detail": "Semantic landmarks: header, main, nav, footer.",
          "evidence": {
            "present": [
              "header",
              "main",
              "nav",
              "footer"
            ],
            "expected": [
              "header",
              "main",
              "nav",
              "footer",
              "article"
            ]
          }
        },
        {
          "id": "heading_hierarchy",
          "label": "Heading hierarchy",
          "status": "pass",
          "score": 1.0,
          "weight": 0.8,
          "detail": "Heading counts: {'h1': 2, 'h2': 5, 'h3': 25, 'h4': 24, 'h5': 0, 'h6': 0}.",
          "evidence": {
            "h1": 2,
            "h2": 5,
            "h3": 25,
            "h4": 24,
            "h5": 0,
            "h6": 0
          }
        },
        {
          "id": "text_extractable",
          "label": "Text content extractable",
          "status": "warn",
          "score": 0.5,
          "weight": 2.0,
          "detail": "Low text-to-HTML ratio (2.2%, 1864 words). Could be markup-heavy.",
          "evidence": {
            "word_count": 1864,
            "ratio": 0.0221
          }
        },
        {
          "id": "html_lang",
          "label": "<html lang> set",
          "status": "pass",
          "score": 1.0,
          "weight": 0.4,
          "detail": "lang=\"en-US\"",
          "evidence": null
        }
      ],
      "summary": ""
    },
    {
      "id": "citation_probe",
      "label": "Citation Probe",
      "weight": 0.2,
      "score": 0,
      "checks": [
        {
          "id": "probe_gemini",
          "label": "Google Gemini citations",
          "status": "skip",
          "score": 0.0,
          "weight": 0.0,
          "detail": "GEMINI_API_KEY not set \u2014 skipping Gemini probe. Get a free key at https://aistudio.google.com/apikey.",
          "evidence": null
        },
        {
          "id": "probe_mistral",
          "label": "Mistral citations",
          "status": "skip",
          "score": 0.0,
          "weight": 0.0,
          "detail": "MISTRAL_API_KEY not set \u2014 skipping Mistral probe. Get a free key at https://console.mistral.ai/api-keys.",
          "evidence": null
        },
        {
          "id": "probe_brave",
          "label": "Brave Search ranking",
          "status": "skip",
          "score": 0.0,
          "weight": 0.0,
          "detail": "BRAVE_API_KEY not set \u2014 skipping Brave probe. Get a free key at https://brave.com/search/api/.",
          "evidence": null
        },
        {
          "id": "probe_duck_ai",
          "label": "Duck.ai citations (best-effort)",
          "status": "skip",
          "score": 0.0,
          "weight": 0.0,
          "detail": "Couldn't obtain Duck.ai session token (expected \u2014 they rotate often).",
          "evidence": null
        }
      ],
      "summary": ""
    }
  ],
  "fixes": [
    {
      "severity": "minor",
      "category": "agent_access",
      "title": "Add a robots.txt with explicit AI-bot allows",
      "detail": "No named AI bots in robots.txt \u2014 you're relying on wildcard defaults. Add explicit `User-agent: GPTBot` etc. entries to make intent clear.",
      "score_lift": 2,
      "effort": "low",
      "snippet": "User-agent: GPTBot\nAllow: /",
      "snippet_language": "text",
      "docs_url": "https://platform.openai.com/docs/bots"
    },
    {
      "severity": "minor",
      "category": "discoverability",
      "title": "Add an llms-full.txt with your full site content in Markdown",
      "detail": "Optional: add /llms-full.txt with full-content Markdown for richer AI grounding.",
      "score_lift": 1,
      "effort": "medium",
      "docs_url": "https://llmstxt.org/"
    },
    {
      "severity": "minor",
      "category": "content_clarity",
      "title": "Reduce to a single <h1> on your homepage",
      "detail": "2 H1 tags \u2014 ideally just one.",
      "score_lift": 1,
      "effort": "low"
    },
    {
      "severity": "minor",
      "category": "content_clarity",
      "title": "Render meaningful text server-side (avoid JS-only content)",
      "detail": "Low text-to-HTML ratio (2.2%, 1864 words). Could be markup-heavy.",
      "score_lift": 1,
      "effort": "high"
    }
  ],
  "suggested_llms_txt": "# Stripe\n> Financial infrastructure for the internet.\n\n## Key pages\n- [/docs](/docs): documentation\n- [/pricing](/pricing): pricing\n",
  "errors": []
};
