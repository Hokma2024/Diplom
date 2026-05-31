"""Block C — Telemetry signal collectors.

Instruments a service call and captures signals according to the active
ObservabilityConfig.  Collected signals are stored in a SignalStore that
can be queried by the fault detectors and the comparison framework.
"""

from __future__ import annotations

import time
import uuid
import logging
import resource as _resource
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .configs import ObservabilityConfig, ObservabilityLevel, SignalType, TelemetrySignal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signal store (in-memory, per experiment run)
# ---------------------------------------------------------------------------

@dataclass
class SignalStore:
    """Append-only store for telemetry signals collected during a run."""
    signals: List[TelemetrySignal] = field(default_factory=list)

    def add(self, signal: TelemetrySignal) -> None:
        self.signals.append(signal)

    def query(
        self,
        signal_type: Optional[SignalType] = None,
        name: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> List[TelemetrySignal]:
        out = self.signals
        if signal_type:
            out = [s for s in out if s.signal_type == signal_type]
        if name:
            out = [s for s in out if s.name == name]
        if trace_id:
            out = [s for s in out if s.trace_id == trace_id]
        return out

    def clear(self) -> None:
        self.signals.clear()

    @property
    def metric_count(self) -> int:
        return sum(1 for s in self.signals if s.signal_type == SignalType.METRIC)

    @property
    def log_count(self) -> int:
        return sum(1 for s in self.signals if s.signal_type == SignalType.LOG)

    @property
    def trace_count(self) -> int:
        return sum(1 for s in self.signals if s.signal_type == SignalType.TRACE)


# ---------------------------------------------------------------------------
# Collector — wraps a callable and emits signals
# ---------------------------------------------------------------------------

class TelemetryCollector:
    """Wraps service calls and collects telemetry signals based on config."""

    def __init__(self, config: ObservabilityConfig, store: Optional[SignalStore] = None):
        self.config = config
        self.store = store or SignalStore()
        self._active_trace_id: Optional[str] = None

    def begin_trace(self) -> str:
        """Start a new trace context.  Returns trace_id."""
        tid = uuid.uuid4().hex[:16]
        self._active_trace_id = tid
        return tid

    def end_trace(self) -> None:
        self._active_trace_id = None

    # -- core instrumented call --

    def instrument_call(
        self,
        func: Callable[..., Any],
        *args: Any,
        call_name: str = "",
        **kwargs: Any,
    ) -> Any:
        """Execute *func* and collect signals permitted by the config."""
        call_name = call_name or getattr(func, "__name__", "unknown")
        span_id = uuid.uuid4().hex[:8]
        trace_id = self._active_trace_id

        # Pre-call resource snapshot (O2 only)
        pre_rusage = None
        if self.config.collect_resource_metrics:
            pre_rusage = _resource.getrusage(_resource.RUSAGE_SELF)

        t0 = time.perf_counter()
        error: Optional[Exception] = None
        result: Any = None
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as exc:
            error = exc
            raise
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._emit_signals(
                call_name=call_name,
                elapsed_ms=elapsed_ms,
                error=error,
                span_id=span_id,
                trace_id=trace_id,
                pre_rusage=pre_rusage,
            )

    async def instrument_async_call(
        self,
        func: Callable[..., Any],
        *args: Any,
        call_name: str = "",
        **kwargs: Any,
    ) -> Any:
        """Async variant of instrument_call."""
        call_name = call_name or getattr(func, "__name__", "unknown")
        span_id = uuid.uuid4().hex[:8]
        trace_id = self._active_trace_id

        pre_rusage = None
        if self.config.collect_resource_metrics:
            pre_rusage = _resource.getrusage(_resource.RUSAGE_SELF)

        t0 = time.perf_counter()
        error: Optional[Exception] = None
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as exc:
            error = exc
            raise
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._emit_signals(
                call_name=call_name,
                elapsed_ms=elapsed_ms,
                error=error,
                span_id=span_id,
                trace_id=trace_id,
                pre_rusage=pre_rusage,
            )

    # -- signal emission logic --

    def _emit_signals(
        self,
        *,
        call_name: str,
        elapsed_ms: float,
        error: Optional[Exception],
        span_id: str,
        trace_id: Optional[str],
        pre_rusage: Any,
    ) -> None:
        ts = time.time()
        base_labels = {"call": call_name}

        # O0: error counters + health
        if self.config.collect_error_counters:
            self.store.add(TelemetrySignal(
                signal_type=SignalType.METRIC,
                name="call_total",
                value=1,
                timestamp=ts,
                labels={**base_labels, "ok": str(error is None)},
                trace_id=trace_id,
                span_id=span_id,
            ))
            if error:
                self.store.add(TelemetrySignal(
                    signal_type=SignalType.METRIC,
                    name="error_total",
                    value=1,
                    timestamp=ts,
                    labels={**base_labels, "error_type": type(error).__name__},
                    trace_id=trace_id,
                    span_id=span_id,
                ))

        if self.config.collect_health_checks:
            self.store.add(TelemetrySignal(
                signal_type=SignalType.METRIC,
                name="health",
                value=0 if error else 1,
                timestamp=ts,
                labels=base_labels,
                trace_id=trace_id,
                span_id=span_id,
            ))

        # O1: latency + structured logs + traces
        if self.config.collect_latency_histograms:
            self.store.add(TelemetrySignal(
                signal_type=SignalType.METRIC,
                name="latency_ms",
                value=elapsed_ms,
                timestamp=ts,
                labels=base_labels,
                trace_id=trace_id,
                span_id=span_id,
            ))

        if self.config.collect_structured_logs:
            log_entry = {
                "call": call_name,
                "elapsed_ms": round(elapsed_ms, 2),
                "ok": error is None,
            }
            if error:
                log_entry["error"] = str(error)
                log_entry["error_type"] = type(error).__name__
            self.store.add(TelemetrySignal(
                signal_type=SignalType.LOG,
                name="call_log",
                value=log_entry,
                timestamp=ts,
                labels=base_labels,
                trace_id=trace_id,
                span_id=span_id,
            ))

        if self.config.collect_traces:
            self.store.add(TelemetrySignal(
                signal_type=SignalType.TRACE,
                name="span",
                value={
                    "call": call_name,
                    "span_id": span_id,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "ok": error is None,
                },
                timestamp=ts,
                labels=base_labels,
                trace_id=trace_id,
                span_id=span_id,
            ))

        # O2: span attributes, correlation, resources, diagnostics
        if self.config.collect_span_attributes and error:
            self.store.add(TelemetrySignal(
                signal_type=SignalType.TRACE,
                name="span_error_attrs",
                value={
                    "error_type": type(error).__name__,
                    "error_msg": str(error)[:500],
                },
                timestamp=ts,
                labels=base_labels,
                trace_id=trace_id,
                span_id=span_id,
            ))

        if self.config.collect_inter_service_correlation and trace_id:
            self.store.add(TelemetrySignal(
                signal_type=SignalType.TRACE,
                name="correlation",
                value={"trace_id": trace_id, "span_id": span_id, "call": call_name},
                timestamp=ts,
                labels=base_labels,
                trace_id=trace_id,
                span_id=span_id,
            ))

        if self.config.collect_resource_metrics and pre_rusage:
            post = _resource.getrusage(_resource.RUSAGE_SELF)
            self.store.add(TelemetrySignal(
                signal_type=SignalType.METRIC,
                name="resource_usage",
                value={
                    "user_time_delta": post.ru_utime - pre_rusage.ru_utime,
                    "sys_time_delta": post.ru_stime - pre_rusage.ru_stime,
                    "max_rss_kb": post.ru_maxrss,
                },
                timestamp=ts,
                labels=base_labels,
                trace_id=trace_id,
                span_id=span_id,
            ))

        if self.config.collect_diagnostic_signals:
            self.store.add(TelemetrySignal(
                signal_type=SignalType.METRIC,
                name="diagnostic",
                value={
                    "call": call_name,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "error": str(error) if error else None,
                    "trace_id": trace_id,
                    "span_id": span_id,
                },
                timestamp=ts,
                labels=base_labels,
                trace_id=trace_id,
                span_id=span_id,
            ))
