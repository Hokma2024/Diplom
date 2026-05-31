"""Block C — Observability configurations O0 / O1 / O2.

Each configuration defines *what* telemetry signals are collected and at what
depth.  The same microservice system is exercised under each configuration
so that fault-detection results can be compared fairly.

O0 — Minimal: only health/error counters
O1 — Medium:  + latency histograms, structured logs, basic traces
O2 — Extended: + detailed span attributes, inter-service correlation,
               resource metrics, custom diagnostic signals
"""

from __future__ import annotations

import enum
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signal types
# ---------------------------------------------------------------------------

class SignalType(str, enum.Enum):
    METRIC = "metric"
    LOG = "log"
    TRACE = "trace"


@dataclass
class TelemetrySignal:
    """Single telemetry signal captured during an experiment run."""
    signal_type: SignalType
    name: str
    value: Any
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Observability level enum
# ---------------------------------------------------------------------------

class ObservabilityLevel(str, enum.Enum):
    O0 = "O0"  # minimal
    O1 = "O1"  # medium
    O2 = "O2"  # extended


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class ObservabilityConfig:
    """Describes a concrete observability configuration."""
    level: ObservabilityLevel
    collect_error_counters: bool = True
    collect_health_checks: bool = True
    collect_latency_histograms: bool = False
    collect_structured_logs: bool = False
    collect_traces: bool = False
    collect_span_attributes: bool = False
    collect_inter_service_correlation: bool = False
    collect_resource_metrics: bool = False
    collect_diagnostic_signals: bool = False

    @property
    def signal_depth(self) -> int:
        """Number of enabled collection dimensions (0–9)."""
        flags = [
            self.collect_error_counters,
            self.collect_health_checks,
            self.collect_latency_histograms,
            self.collect_structured_logs,
            self.collect_traces,
            self.collect_span_attributes,
            self.collect_inter_service_correlation,
            self.collect_resource_metrics,
            self.collect_diagnostic_signals,
        ]
        return sum(flags)


def get_config(level: ObservabilityLevel) -> ObservabilityConfig:
    """Factory: return the canonical config for a given level."""
    if level == ObservabilityLevel.O0:
        return ObservabilityConfig(
            level=ObservabilityLevel.O0,
            collect_error_counters=True,
            collect_health_checks=True,
        )
    if level == ObservabilityLevel.O1:
        return ObservabilityConfig(
            level=ObservabilityLevel.O1,
            collect_error_counters=True,
            collect_health_checks=True,
            collect_latency_histograms=True,
            collect_structured_logs=True,
            collect_traces=True,
        )
    # O2
    return ObservabilityConfig(
        level=ObservabilityLevel.O2,
        collect_error_counters=True,
        collect_health_checks=True,
        collect_latency_histograms=True,
        collect_structured_logs=True,
        collect_traces=True,
        collect_span_attributes=True,
        collect_inter_service_correlation=True,
        collect_resource_metrics=True,
        collect_diagnostic_signals=True,
    )


# Quick sanity: O0 < O1 < O2 in depth
assert get_config(ObservabilityLevel.O0).signal_depth < \
       get_config(ObservabilityLevel.O1).signal_depth < \
       get_config(ObservabilityLevel.O2).signal_depth
