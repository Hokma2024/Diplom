"""Block C + E — Fault / anomaly detectors.

Rules that analyse collected signals from a SignalStore and decide whether
a fault has been detected, how quickly, and how precisely it can be
localised.

Each detector returns a DetectionResult indicating:
- detected: bool
- time_to_detect_ms: latency from fault injection to first alert
- localized: whether the root-cause service/call was identified
- signal_types_used: which signal types contributed
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import List, Optional, Set

from .configs import SignalType, TelemetrySignal
from .collectors import SignalStore


@dataclass
class DetectionResult:
    """Outcome of a single detection attempt."""
    detected: bool = False
    time_to_detect_ms: Optional[float] = None
    localized: bool = False
    localized_call: Optional[str] = None
    signal_types_used: Set[SignalType] = field(default_factory=set)
    details: str = ""


# ---------------------------------------------------------------------------
# Metric-based detector
# ---------------------------------------------------------------------------

class MetricDetector:
    """Detects faults by analysing metric signals (error rate, latency)."""

    def __init__(
        self,
        error_rate_threshold: float = 0.1,
        latency_spike_factor: float = 3.0,
    ):
        self.error_rate_threshold = error_rate_threshold
        self.latency_spike_factor = latency_spike_factor

    def detect(self, store: SignalStore, baseline_latency_ms: Optional[float] = None) -> DetectionResult:
        result = DetectionResult()

        # Error rate check
        calls = store.query(signal_type=SignalType.METRIC, name="call_total")
        errors = [s for s in calls if s.labels.get("ok") == "False"]
        total = len(calls)
        if total > 0:
            err_rate = len(errors) / total
            if err_rate >= self.error_rate_threshold:
                result.detected = True
                result.signal_types_used.add(SignalType.METRIC)
                result.details = f"error_rate={err_rate:.2%} >= {self.error_rate_threshold:.2%}"
                if errors:
                    first_err_ts = min(e.timestamp for e in errors)
                    first_call_ts = min(c.timestamp for c in calls)
                    result.time_to_detect_ms = (first_err_ts - first_call_ts) * 1000.0

                    # Try to localize
                    err_calls = set(e.labels.get("call", "") for e in errors)
                    if len(err_calls) == 1:
                        result.localized = True
                        result.localized_call = err_calls.pop()

        # Latency spike check
        latencies = store.query(signal_type=SignalType.METRIC, name="latency_ms")
        if latencies and baseline_latency_ms and baseline_latency_ms > 0:
            vals = [s.value for s in latencies if isinstance(s.value, (int, float))]
            if vals:
                avg_lat = statistics.mean(vals)
                if avg_lat > baseline_latency_ms * self.latency_spike_factor:
                    result.detected = True
                    result.signal_types_used.add(SignalType.METRIC)
                    if not result.details:
                        result.details = f"latency_spike avg={avg_lat:.1f}ms > {baseline_latency_ms * self.latency_spike_factor:.1f}ms"

        return result


# ---------------------------------------------------------------------------
# Log-based detector
# ---------------------------------------------------------------------------

class LogDetector:
    """Detects faults by analysing structured log entries."""

    def detect(self, store: SignalStore) -> DetectionResult:
        result = DetectionResult()
        logs = store.query(signal_type=SignalType.LOG, name="call_log")
        error_logs = [l for l in logs if isinstance(l.value, dict) and not l.value.get("ok", True)]

        if error_logs:
            result.detected = True
            result.signal_types_used.add(SignalType.LOG)
            first = min(error_logs, key=lambda l: l.timestamp)
            all_logs_ts = min(l.timestamp for l in logs) if logs else first.timestamp
            result.time_to_detect_ms = (first.timestamp - all_logs_ts) * 1000.0
            result.details = f"error_logs={len(error_logs)}"

            err_calls = set()
            for el in error_logs:
                if isinstance(el.value, dict):
                    err_calls.add(el.value.get("call", ""))
            if len(err_calls) == 1:
                result.localized = True
                result.localized_call = err_calls.pop()

        return result


# ---------------------------------------------------------------------------
# Trace-based detector
# ---------------------------------------------------------------------------

class TraceDetector:
    """Detects faults by analysing trace spans."""

    def detect(self, store: SignalStore) -> DetectionResult:
        result = DetectionResult()
        spans = store.query(signal_type=SignalType.TRACE, name="span")
        error_spans = [s for s in spans if isinstance(s.value, dict) and not s.value.get("ok", True)]

        if error_spans:
            result.detected = True
            result.signal_types_used.add(SignalType.TRACE)
            first = min(error_spans, key=lambda s: s.timestamp)
            all_spans_ts = min(s.timestamp for s in spans) if spans else first.timestamp
            result.time_to_detect_ms = (first.timestamp - all_spans_ts) * 1000.0

            err_calls = set()
            for es in error_spans:
                if isinstance(es.value, dict):
                    err_calls.add(es.value.get("call", ""))
            if len(err_calls) == 1:
                result.localized = True
                result.localized_call = err_calls.pop()

            # Check correlation data (O2)
            correlations = store.query(signal_type=SignalType.TRACE, name="correlation")
            if correlations:
                result.signal_types_used.add(SignalType.TRACE)
                result.details = f"error_spans={len(error_spans)}, correlations={len(correlations)}"
            else:
                result.details = f"error_spans={len(error_spans)}"

        return result


# ---------------------------------------------------------------------------
# Combined multi-signal detector
# ---------------------------------------------------------------------------

class CombinedDetector:
    """Aggregates results from metric, log, and trace detectors."""

    def __init__(
        self,
        error_rate_threshold: float = 0.1,
        latency_spike_factor: float = 3.0,
    ):
        self.metric_det = MetricDetector(error_rate_threshold, latency_spike_factor)
        self.log_det = LogDetector()
        self.trace_det = TraceDetector()

    def detect(
        self,
        store: SignalStore,
        baseline_latency_ms: Optional[float] = None,
    ) -> DetectionResult:
        m = self.metric_det.detect(store, baseline_latency_ms)
        l = self.log_det.detect(store)
        t = self.trace_det.detect(store)

        combined = DetectionResult()
        combined.detected = m.detected or l.detected or t.detected
        combined.signal_types_used = m.signal_types_used | l.signal_types_used | t.signal_types_used

        # Best time-to-detect
        ttds = [r.time_to_detect_ms for r in (m, l, t)
                if r.time_to_detect_ms is not None]
        combined.time_to_detect_ms = min(ttds) if ttds else None

        # Localization: prefer trace > log > metric
        for r in (t, l, m):
            if r.localized:
                combined.localized = True
                combined.localized_call = r.localized_call
                break

        details_parts = []
        if m.details:
            details_parts.append(f"metric: {m.details}")
        if l.details:
            details_parts.append(f"log: {l.details}")
        if t.details:
            details_parts.append(f"trace: {t.details}")
        combined.details = "; ".join(details_parts)

        return combined
