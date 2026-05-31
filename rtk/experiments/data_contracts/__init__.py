"""Data contracts — re-exports from :mod:`schemas`."""

from __future__ import annotations

from .schemas import (
    ALL_SCENARIOS,
    BASELINE_SCENARIOS,
    FAULT_SCENARIOS,
    REGRESSION_SCENARIOS,
    AggregatedResult,
    RawRunRecord,
    ScenarioSpec,
    from_dict,
    to_dict,
)

__all__ = [
    "RawRunRecord",
    "AggregatedResult",
    "ScenarioSpec",
    "ALL_SCENARIOS",
    "BASELINE_SCENARIOS",
    "REGRESSION_SCENARIOS",
    "FAULT_SCENARIOS",
    "to_dict",
    "from_dict",
]
