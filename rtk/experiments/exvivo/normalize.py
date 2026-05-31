"""Block D — Normalisation / cleanup of captured interactions.

Before replaying captured interactions as regression tests, unstable fields
must be normalised:
- timestamps → zeroed / relative
- UUIDs / IDs → deterministic placeholders
- nonces / tokens → stripped
- floating-point jitter → rounded

This ensures replay comparisons are stable and meaningful.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .capture import CapturedInteraction, CapturedScenario


@dataclass
class NormalisationConfig:
    """Controls which fields are normalised."""
    zero_timestamps: bool = True
    deterministic_ids: bool = True
    strip_nonces: bool = True
    round_floats_digits: int = 2
    ignore_fields: Set[str] = field(default_factory=lambda: {
        "interaction_id", "timestamp", "elapsed_ms", "trace_id",
    })
    id_patterns: List[str] = field(default_factory=lambda: [
        r"[0-9a-f]{8,}",
        r"[0-9a-f]{4}(-[0-9a-f]{4}){3}-[0-9a-f]{12}",
    ])


# ---------------------------------------------------------------------------
# UUID / ID placeholder mapping
# ---------------------------------------------------------------------------

class _IdMapper:
    """Maps original IDs to deterministic placeholders."""

    def __init__(self) -> None:
        self._map: Dict[str, str] = {}
        self._counter = 0

    def get(self, original: str) -> str:
        if original not in self._map:
            self._counter += 1
            self._map[original] = f"ID_{self._counter:04d}"
        return self._map[original]


# ---------------------------------------------------------------------------
# Normaliser
# ---------------------------------------------------------------------------

class InteractionNormaliser:
    """Normalises captured interactions for stable replay comparison."""

    def __init__(self, config: Optional[NormalisationConfig] = None):
        self.config = config or NormalisationConfig()
        self._id_mapper = _IdMapper()

    def normalise_scenario(self, scenario: CapturedScenario) -> CapturedScenario:
        """Return a new normalised copy of the scenario."""
        normalised = CapturedScenario(
            scenario_id=self._norm_id(scenario.scenario_id),
            name=scenario.name,
            started_at=0.0 if self.config.zero_timestamps else scenario.started_at,
            finished_at=None,
            metadata=self._norm_dict(scenario.metadata),
            interactions=[
                self.normalise_interaction(ix, idx)
                for idx, ix in enumerate(scenario.interactions)
            ],
        )
        return normalised

    def normalise_interaction(
        self, ix: CapturedInteraction, index: int = 0,
    ) -> CapturedInteraction:
        return CapturedInteraction(
            interaction_id=f"IX_{index:04d}",
            timestamp=0.0 if self.config.zero_timestamps else ix.timestamp,
            call_name=ix.call_name,
            arguments=self._norm_dict(ix.arguments),
            response=self._norm_value(ix.response),
            error=ix.error,
            error_type=ix.error_type,
            elapsed_ms=0.0 if self.config.zero_timestamps else ix.elapsed_ms,
            trace_id=self._norm_id(ix.trace_id) if ix.trace_id else None,
            request_context=self._norm_dict(ix.request_context),
        )

    # -- internal helpers --

    def _norm_id(self, val: str) -> str:
        if not self.config.deterministic_ids:
            return val
        return self._id_mapper.get(val)

    def _norm_value(self, val: Any) -> Any:
        if val is None:
            return None
        if isinstance(val, str):
            return self._norm_string(val)
        if isinstance(val, (int, bool)):
            return val
        if isinstance(val, float):
            return round(val, self.config.round_floats_digits)
        if isinstance(val, dict):
            return self._norm_dict(val)
        if isinstance(val, (list, tuple)):
            return [self._norm_value(x) for x in val]
        return str(val)

    def _norm_dict(self, d: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k, v in d.items():
            if k in self.config.ignore_fields:
                continue
            out[k] = self._norm_value(v)
        return out

    def _norm_string(self, s: str) -> str:
        result = s
        if self.config.deterministic_ids:
            for pat in self.config.id_patterns:
                result = re.sub(pat, lambda m: self._id_mapper.get(m.group()), result)
        return result
