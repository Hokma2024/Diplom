"""Case-study artifact builder.

Given a ``scenario_id`` and optionally a ``run_id``, this module collects
the raw-run records, assembles a narrative timeline, and persists a
self-contained case-study artifact that can be embedded in the diploma text
or displayed in a Grafana / Dash dashboard.

Usage::

    python -m experiments.casestudy.builder \\
        --results experiments/results/raw_runs.jsonl \\
        --scenario REG-001 \\
        --output experiments/results/casestudies/

Programmatic API::

    from experiments.casestudy.builder import build_case_study
    artifact = build_case_study(runs, scenario_id="REG-001")
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from experiments.data_contracts.schemas import RawRunRecord


# ------------------------------------------------------------------
# Data model
# ------------------------------------------------------------------

@dataclass
class TimelineEvent:
    """Single event on the case-study timeline."""

    timestamp: str
    event_type: str          # e.g. "injection", "detection", "localization"
    description: str
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseStudyArtifact:
    """Self-contained case-study for one scenario."""

    scenario_id: str
    scenario_group: str
    scenario_name: str
    description: str
    run_ids: List[str]
    total_repeats: int
    modes_tested: List[str]
    obs_levels_tested: List[str]

    # Core findings
    detection_rate: float
    localization_rate: float
    mean_time_to_detect_ms: float
    mean_time_to_localize_ms: float
    signal_types_used: List[str]

    # Overhead snapshot
    mean_latency_ms: float
    mean_throughput_rps: float
    mean_resource_overhead_kb: float

    # Timeline of key events (reconstructed from runs)
    timeline: List[TimelineEvent] = field(default_factory=list)

    # Metadata
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ------------------------------------------------------------------
# Builder logic
# ------------------------------------------------------------------

def _safe_mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_case_study(
    runs: List[RawRunRecord],
    scenario_id: str,
) -> CaseStudyArtifact:
    """Build a :class:`CaseStudyArtifact` from a list of raw-run records.

    Filters *runs* to those matching *scenario_id* and assembles a
    comprehensive case-study artifact.
    """
    filtered = [r for r in runs if r.scenario_id == scenario_id]
    if not filtered:
        return CaseStudyArtifact(
            scenario_id=scenario_id,
            scenario_group="",
            scenario_name="",
            description="No runs found for this scenario.",
            run_ids=[],
            total_repeats=0,
            modes_tested=[],
            obs_levels_tested=[],
            detection_rate=0.0,
            localization_rate=0.0,
            mean_time_to_detect_ms=0.0,
            mean_time_to_localize_ms=0.0,
            signal_types_used=[],
            mean_latency_ms=0.0,
            mean_throughput_rps=0.0,
            mean_resource_overhead_kb=0.0,
        )

    first = filtered[0]
    run_ids = [r.run_id for r in filtered]
    modes = sorted(set(r.mode for r in filtered))
    obs_levels = sorted(set(r.obs_level for r in filtered))

    detections = [r.actual_detection for r in filtered]
    localizations = [r.actual_localization for r in filtered]
    ttd = [r.time_to_detect_ms for r in filtered if r.time_to_detect_ms is not None]
    ttl = [r.time_to_localize_ms for r in filtered if r.time_to_localize_ms is not None]

    all_signals: List[str] = []
    for r in filtered:
        if r.signal_types_used:
            all_signals.extend(r.signal_types_used.split(","))
    unique_signals = sorted(set(s.strip() for s in all_signals if s.strip()))

    detection_rate = sum(1 for d in detections if d) / len(detections) if detections else 0.0
    localization_rate = sum(1 for l in localizations if l) / len(localizations) if localizations else 0.0

    # Build timeline events from runs
    timeline: List[TimelineEvent] = []
    for r in filtered:
        timeline.append(TimelineEvent(
            timestamp=r.timestamp,
            event_type="run",
            description=f"Mode={r.mode} Obs={r.obs_level} Repeat={r.repeat_idx}",
            metrics={
                "detected": r.actual_detection,
                "localized": r.actual_localization,
                "ttd_ms": r.time_to_detect_ms,
                "ttl_ms": r.time_to_localize_ms,
                "latency_mean_ms": r.latency_mean_ms,
            },
        ))
        if r.actual_detection:
            timeline.append(TimelineEvent(
                timestamp=r.timestamp,
                event_type="detection",
                description=f"Fault detected in mode {r.mode} (obs={r.obs_level})",
                metrics={"ttd_ms": r.time_to_detect_ms},
            ))
        if r.actual_localization:
            timeline.append(TimelineEvent(
                timestamp=r.timestamp,
                event_type="localization",
                description=f"Fault localized in mode {r.mode} (obs={r.obs_level})",
                metrics={"ttl_ms": r.time_to_localize_ms},
            ))

    return CaseStudyArtifact(
        scenario_id=scenario_id,
        scenario_group=first.scenario_group,
        scenario_name=first.scenario_id,
        description=f"Case study for {scenario_id} across {len(filtered)} runs.",
        run_ids=run_ids,
        total_repeats=len(filtered),
        modes_tested=modes,
        obs_levels_tested=obs_levels,
        detection_rate=round(detection_rate, 4),
        localization_rate=round(localization_rate, 4),
        mean_time_to_detect_ms=round(_safe_mean(ttd), 2),
        mean_time_to_localize_ms=round(_safe_mean(ttl), 2),
        signal_types_used=unique_signals,
        mean_latency_ms=round(_safe_mean([r.latency_mean_ms for r in filtered]), 2),
        mean_throughput_rps=round(_safe_mean([r.throughput_rps for r in filtered]), 2),
        mean_resource_overhead_kb=round(_safe_mean([r.resource_overhead_kb for r in filtered]), 2),
        timeline=timeline,
    )


def save_case_study(
    artifact: CaseStudyArtifact,
    output_dir: Union[str, Path] = "experiments/results/casestudies",
) -> Path:
    """Persist a case-study artifact as JSON."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{artifact.scenario_id}_case_study.json"
    path.write_text(artifact.to_json(), encoding="utf-8")
    return path


def build_and_save_case_studies(
    runs: List[RawRunRecord],
    regression_id: str = "REG-001",
    fault_id: str = "FLT-003",
    output_dir: Union[str, Path] = "experiments/results/casestudies",
) -> List[Path]:
    """Build and save the minimum required case studies (1 regression + 1 fault)."""
    paths: List[Path] = []
    for sid in (regression_id, fault_id):
        art = build_case_study(runs, sid)
        if art.total_repeats > 0:
            paths.append(save_case_study(art, output_dir))
    return paths
