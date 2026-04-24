"""Heuristic scanners — each returns a list of CheckResult objects."""
from .agent_access import check_agent_access
from .content_clarity import check_content_clarity
from .discoverability import check_discoverability
from .structured_data import check_structured_data

__all__ = [
    "check_agent_access",
    "check_content_clarity",
    "check_discoverability",
    "check_structured_data",
]
