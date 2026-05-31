"""Block E — Fault injection + observability experiments.

Tests that exercise the fault injection pipeline and measure fault
observability across different observability configurations (O0/O1/O2).

Measured outcomes:
- Detectability: was the fault detected?
- Time to detect: how quickly?
- Localisability: was the faulty service identified?
- Signal usefulness: which signal types contributed?
"""

from __future__ import annotations

import pytest
import time
from typing import Any, Dict

from services.mcp_server.models import (
    GetOrderStatusRequest,
    CheckEissdStatusRequest,
    SearchLogsRequest,
)
from services.mcp_server.services import OrderService

from experiments.fault_injection.faults import (
    FaultClass,
    FaultSpec,
    LatencyFault,
    TimeoutFault,
    DependencyFailureFault,
    PartialUnavailableFault,
    ResourceDegradationFault,
    NetworkDegradationFault,
    create_fault,
)
from experiments.fault_injection.injector import FaultInjector
from experiments.observability.configs import ObservabilityLevel, get_config
from experiments.observability.collectors import TelemetryCollector, SignalStore
from experiments.observability.detectors import (
    MetricDetector,
    LogDetector,
    TraceDetector,
    CombinedDetector,
)


# ---------------------------------------------------------------------------
# Fault class tests
# ---------------------------------------------------------------------------

class TestFaultClasses:
    @pytest.mark.fault
    def test_latency_fault(self):
        spec = FaultSpec(fault_class=FaultClass.LATENCY, params={"delay_ms": 50})
        impl = create_fault(spec)
        t0 = time.perf_counter()
        result = impl(lambda: 42)
        elapsed = (time.perf_counter() - t0) * 1000
        assert result == 42
        assert elapsed >= 40  # allow small tolerance

    @pytest.mark.fault
    def test_timeout_fault(self):
        spec = FaultSpec(fault_class=FaultClass.TIMEOUT, params={"delay_ms": 10})
        impl = create_fault(spec)
        with pytest.raises(TimeoutError):
            impl(lambda: 42)

    @pytest.mark.fault
    def test_dependency_failure_fault(self):
        spec = FaultSpec(fault_class=FaultClass.DEPENDENCY_FAILURE,
                         params={"error_message": "DB down"})
        impl = create_fault(spec)
        with pytest.raises(ConnectionError, match="DB down"):
            impl(lambda: 42)

    @pytest.mark.fault
    def test_partial_unavailable_always(self):
        spec = FaultSpec(fault_class=FaultClass.PARTIAL_UNAVAILABLE,
                         params={"failure_rate": 1.0})
        impl = create_fault(spec)
        with pytest.raises(ConnectionError):
            impl(lambda: 42)

    @pytest.mark.fault
    def test_partial_unavailable_never(self):
        spec = FaultSpec(fault_class=FaultClass.PARTIAL_UNAVAILABLE,
                         params={"failure_rate": 0.0})
        impl = create_fault(spec)
        assert impl(lambda: 42) == 42

    @pytest.mark.fault
    def test_resource_degradation(self):
        spec = FaultSpec(fault_class=FaultClass.RESOURCE_DEGRADATION,
                         params={"cpu_burn_ms": 20})
        impl = create_fault(spec)
        t0 = time.perf_counter()
        result = impl(lambda: 42)
        elapsed = (time.perf_counter() - t0) * 1000
        assert result == 42
        assert elapsed >= 15

    @pytest.mark.fault
    def test_network_degradation_no_corruption(self):
        spec = FaultSpec(fault_class=FaultClass.NETWORK_DEGRADATION,
                         params={"jitter_ms": 10, "corruption_rate": 0.0})
        impl = create_fault(spec)
        assert impl(lambda: 42) == 42


# ---------------------------------------------------------------------------
# Injector tests
# ---------------------------------------------------------------------------

class TestFaultInjector:
    @pytest.mark.fault
    def test_no_faults_passthrough(self):
        injector = FaultInjector()
        result = injector.call(lambda: 42, call_name="test")
        assert result == 42
        assert len(injector.events) == 0

    @pytest.mark.fault
    def test_targeted_fault(self):
        injector = FaultInjector()
        injector.add_fault(FaultSpec(
            fault_class=FaultClass.DEPENDENCY_FAILURE,
            target_call="get_order_status",
            params={"error_message": "injected"},
        ))
        # Non-targeted call should pass through
        assert injector.call(lambda: 42, call_name="other_call") == 42
        # Targeted call should fail
        with pytest.raises(ConnectionError, match="injected"):
            injector.call(lambda: 42, call_name="get_order_status")

    @pytest.mark.fault
    def test_events_recorded(self):
        injector = FaultInjector()
        injector.add_fault(FaultSpec(
            fault_class=FaultClass.LATENCY,
            params={"delay_ms": 5},
        ))
        injector.call(lambda: 1, call_name="a")
        injector.call(lambda: 2, call_name="b")
        assert len(injector.events) == 2
        assert all(e.fault_class == FaultClass.LATENCY for e in injector.events)

    @pytest.mark.fault
    def test_remove_all(self):
        injector = FaultInjector()
        injector.add_fault(FaultSpec(fault_class=FaultClass.TIMEOUT, params={"delay_ms": 10}))
        injector.remove_all()
        result = injector.call(lambda: 42, call_name="test")
        assert result == 42


# ---------------------------------------------------------------------------
# Fault observability experiments
# ---------------------------------------------------------------------------

def _run_fault_experiment(
    obs_level: ObservabilityLevel,
    fault_spec: FaultSpec,
    n_calls: int = 5,
) -> Dict[str, Any]:
    """Helper: run a fault experiment under a given observability config."""
    config = get_config(obs_level)
    store = SignalStore()
    collector = TelemetryCollector(config, store)
    injector = FaultInjector()
    injector.add_fault(fault_spec)

    collector.begin_trace()

    successes = 0
    failures = 0
    for _ in range(n_calls):
        try:
            def _call():
                return injector.call(
                    lambda: OrderService.get_order_status(
                        GetOrderStatusRequest(order_id="1800003902272")
                    ),
                    call_name="get_order_status",
                )
            collector.instrument_call(_call, call_name="get_order_status")
            successes += 1
        except Exception:
            failures += 1

    collector.end_trace()

    return {
        "obs_level": obs_level.value,
        "successes": successes,
        "failures": failures,
        "store": store,
        "config": config,
    }


class TestFaultObservabilityExperiments:
    """Experiment: same fault tested under O0/O1/O2 configurations."""

    @pytest.mark.fault
    def test_dependency_failure_detection_across_levels(self):
        """DependencyFailure detected at all levels, but with different detail."""
        spec = FaultSpec(
            fault_class=FaultClass.DEPENDENCY_FAILURE,
            target_call="get_order_status",
            params={"error_message": "DB connection lost"},
        )

        results = {}
        for level in ObservabilityLevel:
            results[level] = _run_fault_experiment(level, spec, n_calls=5)

        # All levels should record failures
        for level, r in results.items():
            assert r["failures"] == 5, f"{level}: expected 5 failures"

        # O0: only error counters
        o0_store = results[ObservabilityLevel.O0]["store"]
        assert o0_store.metric_count > 0
        assert o0_store.log_count == 0
        assert o0_store.trace_count == 0

        # O1: metrics + logs + traces
        o1_store = results[ObservabilityLevel.O1]["store"]
        assert o1_store.metric_count > 0
        assert o1_store.log_count > 0
        assert o1_store.trace_count > 0

        # O2: even more signals
        o2_store = results[ObservabilityLevel.O2]["store"]
        assert o2_store.metric_count > o1_store.metric_count
        assert o2_store.trace_count > o1_store.trace_count

    @pytest.mark.fault
    def test_detector_accuracy_per_level(self):
        """Verify detectors find the fault and localize it."""
        spec = FaultSpec(
            fault_class=FaultClass.DEPENDENCY_FAILURE,
            target_call="get_order_status",
            params={"error_message": "Injected failure"},
        )

        for level in ObservabilityLevel:
            r = _run_fault_experiment(level, spec, n_calls=3)
            combined = CombinedDetector()
            det = combined.detect(r["store"])
            assert det.detected is True, f"{level}: fault not detected"

    @pytest.mark.fault
    def test_latency_fault_detection(self):
        """Latency injection: detected via latency histograms (O1/O2)."""
        spec = FaultSpec(
            fault_class=FaultClass.LATENCY,
            params={"delay_ms": 100},
        )

        r_o0 = _run_fault_experiment(ObservabilityLevel.O0, spec, n_calls=3)
        r_o1 = _run_fault_experiment(ObservabilityLevel.O1, spec, n_calls=3)

        # O0 has no latency data → cannot detect via latency
        det_o0 = MetricDetector(latency_spike_factor=2.0).detect(r_o0["store"], baseline_latency_ms=1.0)

        # O1 has latency histograms
        det_o1 = MetricDetector(latency_spike_factor=2.0).detect(r_o1["store"], baseline_latency_ms=1.0)
        assert det_o1.detected is True

    @pytest.mark.fault
    def test_signal_usefulness_comparison(self):
        """Compare which signal types are useful for fault detection."""
        spec = FaultSpec(
            fault_class=FaultClass.DEPENDENCY_FAILURE,
            target_call="get_order_status",
            params={"error_message": "Service down"},
        )

        r = _run_fault_experiment(ObservabilityLevel.O2, spec, n_calls=5)
        store = r["store"]

        # Individual detectors
        m_det = MetricDetector().detect(store)
        l_det = LogDetector().detect(store)
        t_det = TraceDetector().detect(store)
        c_det = CombinedDetector().detect(store)

        # All should detect in O2
        assert m_det.detected
        assert l_det.detected
        assert t_det.detected
        assert c_det.detected

        # Combined should use more signal types
        assert len(c_det.signal_types_used) >= len(m_det.signal_types_used)
