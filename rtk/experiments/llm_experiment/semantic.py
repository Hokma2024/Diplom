"""Semantic correctness checker for LLM planning output.

Standard observability (O0/O1/O2) can only see infrastructure signals:
errors, latency, and traces.  It cannot verify *what* the agent decided
to do — only whether calls succeeded.

This module implements a thin semantic layer that answers:
«Did the agent call the right diagnostic tools?»

This is the key detector that the experiment shows is *necessary* to
catch LLM-quality faults that are invisible to O0/O1/O2.
"""

from __future__ import annotations

from typing import List

from common.models import ActionLogEntry


# Tools that constitute a correct diagnostic for an order-status ticket.
# At least one of these must be called successfully.
EXPECTED_DIAGNOSTIC_TOOLS = frozenset({"get_order_status", "check_eissd_status"})


class SemanticChecker:
    """Checks whether planning actions reflect correct diagnostic behaviour."""

    def check(self, actions: List[ActionLogEntry]) -> bool:
        """Return True iff at least one expected diagnostic tool was called OK."""
        return any(
            a.tool in EXPECTED_DIAGNOSTIC_TOOLS and a.ok
            for a in actions
        )

    def describe(self, actions: List[ActionLogEntry]) -> str:
        """Human-readable summary for reporting."""
        if not actions:
            return "no_actions"
        ok_tools = [a.tool for a in actions if a.ok]
        failed_tools = [a.tool for a in actions if not a.ok]
        diagnostic_hit = [t for t in ok_tools if t in EXPECTED_DIAGNOSTIC_TOOLS]
        if diagnostic_hit:
            return f"ok:{diagnostic_hit}"
        parts = []
        if ok_tools:
            parts.append(f"ok_but_wrong:{ok_tools}")
        if failed_tools:
            parts.append(f"failed:{failed_tools}")
        return "; ".join(parts) or "unknown"
