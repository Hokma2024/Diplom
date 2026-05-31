"""Block D — Replay engine for ex-vivo regression testing.

Takes normalised captured scenarios and replays them against the current
system, comparing responses to detect regressions.

Key concepts:
- ReplayResult: outcome of replaying one interaction
- ScenarioReplayResult: aggregated outcome for a whole scenario
- ReplayEngine: orchestrates replay + comparison
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .capture import CapturedInteraction, CapturedScenario
from .normalize import InteractionNormaliser, NormalisationConfig


@dataclass
class ReplayResult:
    """Result of replaying a single interaction."""
    interaction_index: int = 0
    call_name: str = ""
    expected_response: Any = None
    actual_response: Any = None
    match: bool = False
    expected_error: Optional[str] = None
    actual_error: Optional[str] = None
    error_match: bool = True
    elapsed_ms: float = 0.0
    diff_details: str = ""


@dataclass
class ScenarioReplayResult:
    """Aggregated result for replaying an entire scenario."""
    scenario_name: str = ""
    total_interactions: int = 0
    matched: int = 0
    mismatched: int = 0
    errors: int = 0
    replay_results: List[ReplayResult] = field(default_factory=list)
    elapsed_ms: float = 0.0

    @property
    def match_rate(self) -> float:
        return self.matched / self.total_interactions if self.total_interactions else 0.0

    @property
    def has_regressions(self) -> bool:
        return self.mismatched > 0 or self.errors > 0


class ReplayEngine:
    """Replays captured scenarios against the live system.

    The engine receives a *dispatcher* — a callable that accepts
    ``(call_name, arguments)`` and returns the service response.
    This allows testing against the real services or mocked ones.
    """

    def __init__(
        self,
        dispatcher: Callable[[str, Dict[str, Any]], Any],
        normaliser: Optional[InteractionNormaliser] = None,
    ):
        self.dispatcher = dispatcher
        self.normaliser = normaliser or InteractionNormaliser()

    def replay_scenario(self, scenario: CapturedScenario) -> ScenarioReplayResult:
        """Replay every interaction in the scenario and compare."""
        t0 = time.perf_counter()
        result = ScenarioReplayResult(
            scenario_name=scenario.name,
            total_interactions=len(scenario.interactions),
        )

        for idx, ix in enumerate(scenario.interactions):
            rr = self._replay_interaction(ix, idx)
            result.replay_results.append(rr)
            if rr.match and rr.error_match:
                result.matched += 1
            elif rr.actual_error and not rr.expected_error:
                result.errors += 1
            else:
                result.mismatched += 1

        result.elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return result

    def _replay_interaction(self, ix: CapturedInteraction, idx: int) -> ReplayResult:
        rr = ReplayResult(
            interaction_index=idx,
            call_name=ix.call_name,
            expected_response=ix.response,
            expected_error=ix.error,
        )

        t0 = time.perf_counter()
        try:
            actual = self.dispatcher(ix.call_name, ix.arguments)
            rr.actual_response = actual
        except Exception as exc:
            rr.actual_error = str(exc)
        rr.elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Compare errors
        if ix.error and rr.actual_error:
            rr.error_match = True
        elif not ix.error and not rr.actual_error:
            rr.error_match = True
        else:
            rr.error_match = False

        # Compare responses (after normalisation)
        if rr.error_match and not rr.actual_error:
            norm_expected = self.normaliser._norm_value(ix.response)
            norm_actual = self.normaliser._norm_value(rr.actual_response)
            rr.match = _deep_equals(norm_expected, norm_actual)
            if not rr.match:
                rr.diff_details = _describe_diff(norm_expected, norm_actual)
        elif rr.error_match and rr.actual_error:
            rr.match = True
        else:
            rr.match = False
            rr.diff_details = f"error mismatch: expected={ix.error}, actual={rr.actual_error}"

        return rr


def _deep_equals(a: Any, b: Any) -> bool:
    """Structural equality with tolerance for floats."""
    if type(a) != type(b):
        return False
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_deep_equals(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_deep_equals(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return abs(a - b) < 1e-6
    return a == b


def _describe_diff(expected: Any, actual: Any) -> str:
    """Human-readable summary of differences."""
    if type(expected) != type(actual):
        return f"type mismatch: {type(expected).__name__} vs {type(actual).__name__}"
    if isinstance(expected, dict):
        missing = set(expected) - set(actual)
        extra = set(actual) - set(expected)
        changed = [k for k in set(expected) & set(actual) if not _deep_equals(expected[k], actual[k])]
        parts = []
        if missing:
            parts.append(f"missing keys: {missing}")
        if extra:
            parts.append(f"extra keys: {extra}")
        if changed:
            parts.append(f"changed keys: {changed}")
        return "; ".join(parts) or "unknown dict diff"
    if isinstance(expected, (list, tuple)):
        return f"list length: {len(expected)} vs {len(actual)}"
    return f"value: {expected!r} vs {actual!r}"
