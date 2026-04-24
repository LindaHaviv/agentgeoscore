"""Live citation probes. Each probe runs a few natural queries about the site's
topic and reports whether the target domain appeared in the returned citations.

All probes degrade gracefully: if a key is missing or the provider errors, the
probe returns a SKIP result instead of failing the whole scan.
"""
from .brave import probe_brave
from .duck_ai import probe_duck_ai
from .gemini import probe_gemini
from .groq import probe_groq
from .mistral import probe_mistral
from .queries import derive_queries

__all__ = [
    "derive_queries",
    "probe_brave",
    "probe_duck_ai",
    "probe_gemini",
    "probe_groq",
    "probe_mistral",
]
