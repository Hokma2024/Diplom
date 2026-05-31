"""Comparison framework — Experiment runner for A0/A1/A2/A3 modes."""

from __future__ import annotations

import copy
import time
from typing import Any, Optional

from services.mcp_server import storage as _storage
from services.mcp_server.models import (
    GetOrderStatusRequest,
    OrderStatus,
    SearchLogsRequest,
)
from services.mcp_server.services import OrderService

from experiments.observability.configs import ObservabilityLevel, get_config
from experiments.observability.collectors import TelemetryCollector, SignalStore
from experiments.observability.detectors import CombinedDetector
from experiments.exvivo.capture import InteractionCapture
from experiments.exvivo.replay import ReplayEngine
from experiments.fault_injection.faults import FaultClass, FaultSpec
from experiments.fault_injection.injector import FaultInjector
from experiments.overhead.benchmark import run_benchmark, compare_overhead
from experiments.comparison.metrics import (
    TestingMetrics,
    DiagnosticMetrics,
    OverheadMetrics,
    ExVivoMetrics,
    ExperimentResult,
)
from experiments.shared import service_dispatcher, fault_params_for

# Pristine storage snapshot for state reset between runs
_ORIG_ORDERS_DB = copy.deepcopy(_storage.ORDERS_DB)
_ORIG_LOGS_DB = copy.deepcopy(_storage.LOGS_DB)
_ORIG_EISSD_DB = copy.deepcopy(_storage.EISSD_DB)


def _reset() -> None:
    _storage.ORDERS_DB.clear()
    _storage.ORDERS_DB.update(copy.deepcopy(_ORIG_ORDERS_DB))
    _storage.LOGS_DB.clear()
    _storage.LOGS_DB.update(copy.deepcopy(_ORIG_LOGS_DB))
    _storage.EISSD_DB.clear()
    _storage.EISSD_DB.update(copy.deepcopy(_ORIG_EISSD_DB))


def _run_baseline_scenario() -> TestingMetrics:
    t0 = time.perf_counter()
    defects = 0
    passed = 0
    total = 0

    total += 1
    try:
        resp = OrderService.search_logs(
            SearchLogsRequest(order_id="1800003902272", pattern="ORDER_STATUS_DENIED")
        )
        assert resp.error_found is True
        passed += 1
    except Exception:
        defects += 1

    total += 1
    try:
        resp = OrderService.get_order_status(GetOrderStatusRequest(order_id="1800003902272"))
        assert resp.status == OrderStatus.DENIED
        passed += 1
    except Exception:
        defects += 1

    total += 1
    try:
        from services.mcp_server.models import CheckEissdStatusRequest
        resp = OrderService.check_eissd_status(
            CheckEissdStatusRequest(order_id="1800003902272")
        )
        assert resp.status == OrderStatus.IN_PROGRESS
        passed += 1
    except Exception:
        defects += 1

    total += 1
    try:
        OrderService.get_order_status(GetOrderStatusRequest(order_id="NONE"))
        defects += 1
    except ValueError:
        passed += 1

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestingMetrics(
        defects_found=defects,
        total_tests=total,
        passed_tests=passed,
        failed_tests=total - passed,
        execution_time_ms=elapsed,
        reproducibility_rate=1.0,
    )


def run_a0() -> ExperimentResult:
    """A0: Classical baseline testing only."""
    _reset()
    testing = _run_baseline_scenario()
    return ExperimentResult(mode="A0", testing=testing)


def run_a1() -> ExperimentResult:
    """A1: Baseline + Ex-vivo regression.

    Demonstrates regression detection by:
    1. Capturing golden interactions against pristine storage.
    2. Mutating storage to simulate a regression (status DENIED → IN_PROGRESS).
    3. Replaying — mismatches found → regressions_found > 0.
    4. Restoring storage.
    """
    _reset()
    testing = _run_baseline_scenario()

    # Capture golden state
    cap = InteractionCapture()
    cap.start_scenario("a1_denied_order")
    cap.record_call(
        lambda: OrderService.search_logs(
            SearchLogsRequest(order_id="1800003902272", pattern="ORDER_STATUS_DENIED")
        ).model_dump(),
        call_name="search_logs",
        arguments_dict={"order_id": "1800003902272", "pattern": "ORDER_STATUS_DENIED"},
    )
    cap.record_call(
        lambda: OrderService.get_order_status(
            GetOrderStatusRequest(order_id="1800003902272")
        ).model_dump(),
        call_name="get_order_status",
        arguments_dict={"order_id": "1800003902272"},
    )
    scenario = cap.finish_scenario()

    # Simulate regression: order status changed by a code change
    saved_status = _storage.ORDERS_DB["1800003902272"]["status"]
    _storage.ORDERS_DB["1800003902272"]["status"] = "IN_PROGRESS"

    engine = ReplayEngine(dispatcher=service_dispatcher)
    replay = engine.replay_scenario(scenario)

    # Restore
    _storage.ORDERS_DB["1800003902272"]["status"] = saved_status

    exvivo = ExVivoMetrics(
        total_scenarios=1,
        total_interactions=replay.total_interactions,
        matched_interactions=replay.matched,
        regressions_found=replay.mismatched + replay.errors,
        replay_errors=replay.errors,
        replay_time_ms=replay.elapsed_ms,
    )

    return ExperimentResult(mode="A1", testing=testing, exvivo=exvivo)


def run_a2(obs_level: ObservabilityLevel = ObservabilityLevel.O1) -> ExperimentResult:
    """A2: Baseline + Fault injection + Observability.

    TTD is measured by checking the detector after every instrumented call
    so the value reflects real elapsed time from injection start.
    """
    _reset()
    testing = _run_baseline_scenario()

    config = get_config(obs_level)
    store = SignalStore()
    collector = TelemetryCollector(config, store)

    def _workload_plain() -> None:
        OrderService.get_order_status(GetOrderStatusRequest(order_id="1800003902272"))

    baseline_bench = run_benchmark(_workload_plain, n_calls=10, warmup=2, label="pre_baseline")
    baseline_lat_ms = baseline_bench.mean_latency_ms

    injector = FaultInjector()
    injector.add_fault(FaultSpec(
        fault_class=FaultClass.DEPENDENCY_FAILURE,
        target_call="get_order_status",
        params=fault_params_for(FaultClass.DEPENDENCY_FAILURE),
    ))

    ttd_ms: Optional[float] = None
    t0 = time.perf_counter()
    collector.begin_trace()
    for _ in range(5):
        try:
            def _call() -> Any:
                return injector.call(
                    lambda: OrderService.get_order_status(
                        GetOrderStatusRequest(order_id="1800003902272")
                    ),
                    call_name="get_order_status",
                )
            collector.instrument_call(_call, call_name="get_order_status")
        except Exception:
            pass
        if ttd_ms is None:
            interim = CombinedDetector().detect(store, baseline_latency_ms=baseline_lat_ms)
            if interim.detected:
                ttd_ms = (time.perf_counter() - t0) * 1000.0
    collector.end_trace()
    elapsed_total = (time.perf_counter() - t0) * 1000.0

    det = CombinedDetector().detect(store, baseline_latency_ms=baseline_lat_ms)
    if ttd_ms is not None:
        det.time_to_detect_ms = ttd_ms
    elif det.detected:
        det.time_to_detect_ms = elapsed_total

    diagnostic = DiagnosticMetrics(
        fault_detected=det.detected,
        fault_localized=det.localized,
        localized_call=det.localized_call,
        time_to_detect_ms=det.time_to_detect_ms,
        signal_types_used=det.signal_types_used,
    )

    _reset()
    comp = compare_overhead(_workload_plain, obs_level, n_calls=30, warmup=3)
    overhead = OverheadMetrics(
        latency_overhead_ms=comp.latency_overhead_ms,
        latency_overhead_pct=comp.latency_overhead_pct,
        throughput_overhead_pct=comp.throughput_overhead_pct,
        variance_growth=comp.variance_growth,
    )

    return ExperimentResult(
        mode="A2",
        obs_level=obs_level.value,
        testing=testing,
        diagnostic=diagnostic,
        overhead=overhead,
    )


def run_a3(obs_level: ObservabilityLevel = ObservabilityLevel.O1) -> ExperimentResult:
    """A3: Combined — Baseline + Ex-vivo + Fault injection + Observability."""
    a1 = run_a1()
    a2 = run_a2(obs_level)
    return ExperimentResult(
        mode="A3",
        obs_level=obs_level.value,
        testing=a1.testing,
        exvivo=a1.exvivo,
        diagnostic=a2.diagnostic,
        overhead=a2.overhead,
        metadata={"note": "combined A1+A2"},
    )
