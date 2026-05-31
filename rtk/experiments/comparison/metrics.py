"""Comparison framework — Metrics collection.

Defines the standard metrics used to compare experiment modes:

Testing metrics:
- defects_found, defects_missed, false_positives
- reproducibility_rate, test_execution_cost_ms

Diagnostic metrics:
- time_to_detect_ms, time_to_localize_ms
- diagnosis_accuracy, signal_usefulness

Observability effectiveness:
- fault_distinguishability, detector_stability
- detection_vs_depth

Overhead metrics:
- latency_overhead_ms/pct, throughput_overhead_pct
- resource_overhead_kb, outlier_growth
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from experiments.observability.configs import SignalType


@dataclass
class TestingMetrics:
    """Metrics for testing effectiveness (Block B baseline)."""
    defects_found: int = 0
    defects_missed: int = 0
    false_positives: int = 0
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    execution_time_ms: float = 0.0
    reproducibility_rate: float = 1.0

    @property
    def detection_rate(self) -> float:
        total = self.defects_found + self.defects_missed
        return self.defects_found / total if total > 0 else 0.0

    @property
    def false_positive_rate(self) -> float:
        total = self.defects_found + self.false_positives
        return self.false_positives / total if total > 0 else 0.0


@dataclass
class DiagnosticMetrics:
    """Metrics for diagnostic capability (Block E)."""
    time_to_detect_ms: Optional[float] = None
    time_to_localize_ms: Optional[float] = None
    diagnosis_accuracy: float = 0.0
    signal_types_used: Set[SignalType] = field(default_factory=set)
    fault_detected: bool = False
    fault_localized: bool = False
    localized_call: Optional[str] = None

    @property
    def signal_usefulness_score(self) -> float:
        """0.0–1.0 score based on what was achieved."""
        score = 0.0
        if self.fault_detected:
            score += 0.4
        if self.fault_localized:
            score += 0.3
        if self.time_to_detect_ms is not None and self.time_to_detect_ms < 1000:
            score += 0.15
        if len(self.signal_types_used) >= 2:
            score += 0.15
        return min(1.0, score)


@dataclass
class OverheadMetrics:
    """Metrics for instrumentation overhead (Block F)."""
    latency_overhead_ms: float = 0.0
    latency_overhead_pct: float = 0.0
    throughput_overhead_pct: float = 0.0
    resource_overhead_kb: int = 0
    outlier_growth: float = 1.0
    variance_growth: float = 1.0


@dataclass
class ExVivoMetrics:
    """Metrics for ex-vivo regression (Block D)."""
    total_scenarios: int = 0
    total_interactions: int = 0
    matched_interactions: int = 0
    regressions_found: int = 0
    replay_errors: int = 0
    replay_time_ms: float = 0.0

    @property
    def match_rate(self) -> float:
        return self.matched_interactions / self.total_interactions if self.total_interactions > 0 else 0.0

    @property
    def regression_rate(self) -> float:
        return self.regressions_found / self.total_interactions if self.total_interactions > 0 else 0.0


@dataclass
class ExperimentResult:
    """Aggregated result for a single experiment mode (A0/A1/A2/A3)."""
    mode: str = ""
    obs_level: str = ""
    testing: TestingMetrics = field(default_factory=TestingMetrics)
    diagnostic: DiagnosticMetrics = field(default_factory=DiagnosticMetrics)
    overhead: OverheadMetrics = field(default_factory=OverheadMetrics)
    exvivo: ExVivoMetrics = field(default_factory=ExVivoMetrics)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "obs_level": self.obs_level,
            "testing": {
                "defects_found": self.testing.defects_found,
                "defects_missed": self.testing.defects_missed,
                "false_positives": self.testing.false_positives,
                "detection_rate": round(self.testing.detection_rate, 3),
                "execution_time_ms": round(self.testing.execution_time_ms, 1),
                "reproducibility": round(self.testing.reproducibility_rate, 3),
            },
            "diagnostic": {
                "detected": self.diagnostic.fault_detected,
                "localized": self.diagnostic.fault_localized,
                "time_to_detect_ms": self.diagnostic.time_to_detect_ms,
                "signal_usefulness": round(self.diagnostic.signal_usefulness_score, 3),
            },
            "overhead": {
                "latency_ms": round(self.overhead.latency_overhead_ms, 3),
                "latency_pct": round(self.overhead.latency_overhead_pct, 2),
                "throughput_pct": round(self.overhead.throughput_overhead_pct, 2),
                "variance_growth": round(self.overhead.variance_growth, 2),
            },
            "exvivo": {
                "regressions_found": self.exvivo.regressions_found,
                "match_rate": round(self.exvivo.match_rate, 3),
                "replay_time_ms": round(self.exvivo.replay_time_ms, 1),
            },
        }
