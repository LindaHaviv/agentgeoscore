"""Heuristic scanners — each returns a list of CheckResult objects."""
from .agent_access import check_agent_access
from .citability import check_citability
from .content_clarity import check_content_clarity
from .core_web_vitals import check_core_web_vitals
from .discoverability import check_discoverability
from .hreflang import check_hreflang
from .js_rendering import check_js_rendering
from .multipage import check_multipage_depth
from .structured_data import check_structured_data, extract_jsonld

__all__ = [
    "check_agent_access",
    "check_citability",
    "check_content_clarity",
    "check_core_web_vitals",
    "check_discoverability",
    "check_hreflang",
    "check_js_rendering",
    "check_multipage_depth",
    "check_structured_data",
    "extract_jsonld",
]
