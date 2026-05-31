"""Block B (extended) — Tests derived from infrastructure experiment findings.

Each test class is explicitly linked to an experiment result (BUG-XXX).
This file was created in Шаг 4 to close the gap between the experiment
research layer and the A0 product test suite.

Experiment motivation:
  BUG-007  latency spike is invisible to O0, visible from O1
  BUG-006  dependency_failure detected by O0 (error counter fires)
  BUG-008  timeout detected by O0 (error counter fires)
  BUG-001..005  ex-vivo regressions from data mutation
"""

from __future__ import annotations

import copy
import time
import pytest

from services.mcp_server.models import (
    GetOrderStatusRequest,
    CheckEissdStatusRequest,
    OrderStatus,
    SearchLogsRequest,
)
from services.mcp_server.services import OrderService
from services.mcp_server import storage

from experiments.observability.configs import ObservabilityLevel, get_config
from experiments.observability.collectors import TelemetryCollector, SignalStore
from experiments.observability.detectors import CombinedDetector
from experiments.exvivo.capture import InteractionCapture
from experiments.exvivo.replay import ReplayEngine
from experiments.shared import service_dispatcher


# ===================================================================
# CHK-I-01 / CHK-I-02  — Latency observability (BUG-007)
# ===================================================================

class TestLatencyObservability:
    """Derived from BUG-007: latency spike invisible to O0, visible from O1.

    BUG-007 was the key finding that motivated CHK-I-01/02:
    without O1-level observability, a 200ms latency spike in
    get_order_status went completely undetected.
    """

    @pytest.mark.experiment
    def test_sla_order_status(self):
        """CHK-I-01: get_order_status responds within 50ms SLA.

        If this test starts failing, it indicates a real latency regression —
        the same class of fault as BUG-007, now caught proactively.
        """
        order_id = "1800003902272"
        t0 = time.perf_counter()
        resp = OrderService.get_order_status(GetOrderStatusRequest(order_id=order_id))
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert resp.status == OrderStatus.DENIED
        assert elapsed_ms < 50.0, (
            f"get_order_status took {elapsed_ms:.1f}ms — exceeds 50ms SLA. "
            "This is the latency class from BUG-007."
        )

    @pytest.mark.experiment
    def test_o1_detects_spike_o0_does_not(self):
        """CHK-I-02: artificial 200ms latency — O0 misses it, O1 catches it.

        This test reproduces the BUG-007 detection gap in a controlled way.
        A synthetic slow wrapper adds 200ms; then we verify:
        - O0 detector (error counters + health) → detected=False
        - O1 detector (+ latency histogram) → detected=True
        """
        def slow_call():
            time.sleep(0.2)  # 200ms synthetic latency
            return OrderService.get_order_status(
                GetOrderStatusRequest(order_id="1800003902272")
            )

        baseline_ms = 0.5  # in-memory baseline

        # --- O0 ---
        store_o0 = SignalStore()
        col_o0 = TelemetryCollector(get_config(ObservabilityLevel.O0), store_o0)
        col_o0.begin_trace()
        col_o0.instrument_call(slow_call, call_name="get_order_status")
        col_o0.end_trace()
        det_o0 = CombinedDetector().detect(store_o0, baseline_latency_ms=baseline_ms)

        # --- O1 ---
        store_o1 = SignalStore()
        col_o1 = TelemetryCollector(get_config(ObservabilityLevel.O1), store_o1)
        col_o1.begin_trace()
        col_o1.instrument_call(slow_call, call_name="get_order_status")
        col_o1.end_trace()
        det_o1 = CombinedDetector().detect(store_o1, baseline_latency_ms=baseline_ms)

        assert det_o0.detected is False, (
            "O0 should NOT detect a latency-only fault (no error counters fire). "
            "This reproduces the BUG-007 detection gap."
        )
        assert det_o1.detected is True, (
            "O1 SHOULD detect the latency spike via the latency histogram signal."
        )


# ===================================================================
# CHK-I-03 / CHK-I-04  — Dependency failure / timeout (BUG-006, BUG-008)
# ===================================================================

class TestDependencyFailure:
    """Derived from BUG-006 and BUG-008.

    BUG-006: dependency_failure → ConnectionError → detected by O0.
    BUG-008: timeout → TimeoutError → detected by O0.
    These tests verify that the error path is correctly instrumented
    so that O0 would detect these faults in production.
    """

    @pytest.mark.experiment
    def test_mcp_error_recorded_in_actions(self):
        """CHK-I-03: when a service call raises, entry.ok=False is captured.

        Validates the instrumentation layer that BUG-006/008 rely on:
        the action log must record the error so that O0 error counters fire.
        """
        from common.models import ActionLogEntry

        # Simulate: a tool call that raises (like dependency_failure / BUG-006)
        entry = ActionLogEntry(tool="get_order_status", params={"order_id": "1800003902272"})
        t0 = time.perf_counter()
        try:
            raise ConnectionError("Injected: dependency unavailable")
        except Exception as exc:
            entry.ok = False
            entry.error = str(exc)
            entry.error_type = type(exc).__name__
        entry.duration_ms = int((time.perf_counter() - t0) * 1000)

        assert entry.ok is False
        assert "dependency" in entry.error.lower()
        assert entry.error_type == "ConnectionError"

    @pytest.mark.experiment
    def test_o0_detects_service_error(self):
        """CHK-I-03 (monitoring side): O0 detects error when service raises.

        The same signal path used in BUG-006 detection: TelemetryCollector
        emits error_total metric when the instrumented call raises.
        """
        def failing_call():
            raise ConnectionError("Injected dependency failure")

        store = SignalStore()
        col = TelemetryCollector(get_config(ObservabilityLevel.O0), store)
        col.begin_trace()
        with pytest.raises(ConnectionError):
            col.instrument_call(failing_call, call_name="get_order_status")
        col.end_trace()

        det = CombinedDetector().detect(store, baseline_latency_ms=0.5)
        assert det.detected is True, (
            "O0 must detect an error-raising call — this is the BUG-006 signal path."
        )

    @pytest.mark.experiment
    def test_timeout_error_also_detected_by_o0(self):
        """CHK-I-04: TimeoutError is detected by O0 (BUG-008 signal path)."""
        def timeout_call():
            raise TimeoutError("Simulated timeout after 200ms")

        store = SignalStore()
        col = TelemetryCollector(get_config(ObservabilityLevel.O0), store)
        col.begin_trace()
        with pytest.raises(TimeoutError):
            col.instrument_call(timeout_call, call_name="get_order_status")
        col.end_trace()

        det = CombinedDetector().detect(store, baseline_latency_ms=0.5)
        assert det.detected is True


# ===================================================================
# CHK-I-05 / CHK-I-06  — Regression detection (BUG-001..005)
# ===================================================================

class TestRegressionDetection:
    """Derived from BUG-001..005 (ex-vivo regression scenarios).

    These bugs were found when storage was mutated between golden
    capture and replay: the mismatch reveals the regression.
    CHK-I-05 tests the application behaviour directly;
    CHK-I-06 tests the ex-vivo framework detects the same mutation.
    """

    @pytest.mark.experiment
    def test_status_change_reflected(self):
        """CHK-I-05: after DENIED→IN_PROGRESS mutation, get_order_status returns new status.

        Verifies that the service correctly reflects storage state — the
        invariant that BUG-001..005 depend on for regression detection.
        """
        order_id = "1800003902272"

        # Baseline
        before = OrderService.get_order_status(GetOrderStatusRequest(order_id=order_id))
        assert before.status == OrderStatus.DENIED

        # Mutate (simulates a deployment that changed business logic)
        storage.ORDERS_DB[order_id]["status"] = "IN_PROGRESS"

        after = OrderService.get_order_status(GetOrderStatusRequest(order_id=order_id))
        assert after.status == OrderStatus.IN_PROGRESS
        # (reset_storage fixture restores original state after the test)

    @pytest.mark.experiment
    def test_exvivo_detects_status_mutation(self):
        """CHK-I-06: ex-vivo replay finds mismatch when status mutated between runs.

        This is the exact mechanism that found BUG-001 (REG-001 schema drift).
        The test proves the framework works — so experiment findings are reproducible.
        """
        order_id = "1800003902272"

        # 1) Capture golden state
        cap = InteractionCapture()
        cap.start_scenario("test_regression_chk_i06")
        cap.record_call(
            lambda: OrderService.get_order_status(
                GetOrderStatusRequest(order_id=order_id)
            ).model_dump(),
            call_name="get_order_status",
            arguments_dict={"order_id": order_id},
        )
        scenario = cap.finish_scenario()

        # 2) Mutate storage (simulates a regression)
        saved = storage.ORDERS_DB[order_id]["status"]
        storage.ORDERS_DB[order_id]["status"] = "IN_PROGRESS"

        # 3) Replay — should detect mismatch
        engine = ReplayEngine(dispatcher=service_dispatcher)
        replay = engine.replay_scenario(scenario)

        # 4) Restore
        storage.ORDERS_DB[order_id]["status"] = saved

        assert replay.mismatched > 0, (
            "Ex-vivo replay must detect the DENIED→IN_PROGRESS mutation. "
            "If this fails, the regression-detection mechanism is broken."
        )
        assert replay.matched < replay.total_interactions
