"""Scenario catalog loader.

Loads scenario specifications from external JSON catalog files
(``scenarios/regression_catalog.json`` and ``scenarios/fault_catalog.json``)
and converts them into :class:`ScenarioSpec` dataclass instances.

The loader also accepts the in-memory Python catalogs as a fallback so that
existing code paths continue to work unchanged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from experiments.data_contracts.schemas import ScenarioSpec

# Default catalog directory relative to repository root
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CATALOG_DIR = _REPO_ROOT / "scenarios"


def _spec_from_dict(d: Dict) -> ScenarioSpec:
    """Build a :class:`ScenarioSpec` from a catalog JSON entry."""
    return ScenarioSpec(
        scenario_id=d["scenario_id"],
        scenario_group=d["scenario_group"],
        name=d["name"],
        description=d["description"],
        fault_class=d.get("fault_class", ""),
        fault_target=d.get("fault_target", ""),
        expected_detection=d.get("expected_detection", False),
        expected_localization=d.get("expected_localization", False),
        expected_strongest_mode=d.get("expected_strongest_mode", "A0"),
        relevant_signals=d.get("relevant_signals", []),
    )


def load_regression_catalog(
    catalog_dir: Optional[Path] = None,
) -> List[ScenarioSpec]:
    """Load regression scenarios from ``regression_catalog.json``."""
    catalog_dir = catalog_dir or _DEFAULT_CATALOG_DIR
    path = catalog_dir / "regression_catalog.json"
    with open(path, "r", encoding="utf-8") as fh:
        entries = json.load(fh)
    return [_spec_from_dict(e) for e in entries]


def load_fault_catalog(
    catalog_dir: Optional[Path] = None,
) -> List[ScenarioSpec]:
    """Load fault-injection scenarios from ``fault_catalog.json``."""
    catalog_dir = catalog_dir or _DEFAULT_CATALOG_DIR
    path = catalog_dir / "fault_catalog.json"
    with open(path, "r", encoding="utf-8") as fh:
        entries = json.load(fh)
    return [_spec_from_dict(e) for e in entries]


def load_all_catalogs(
    catalog_dir: Optional[Path] = None,
) -> List[ScenarioSpec]:
    """Load and merge both regression and fault catalogs."""
    return load_regression_catalog(catalog_dir) + load_fault_catalog(catalog_dir)


def scenario_by_id(
    scenarios: List[ScenarioSpec],
) -> Dict[str, ScenarioSpec]:
    """Return a lookup dictionary keyed by ``scenario_id``."""
    return {s.scenario_id: s for s in scenarios}
