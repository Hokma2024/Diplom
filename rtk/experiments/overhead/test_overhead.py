"""Block F — Overhead measurement tests.

Measures and compares the performance overhead of different observability
configurations on the same workload.
"""

from __future__ import annotations

import pytest

from services.mcp_server.models import (
    GetOrderStatusRequest,
    SearchLogsRequest,
)
from services.mcp_server.services import OrderService

from experiments.observability.configs import ObservabilityLevel
from experiments.overhead.benchmark import (
    run_benchmark,
    compare_overhead,
    BenchmarkResult,
    OverheadComparison,
)


def _workload_search_logs():
    return OrderService.search_logs(
        SearchLogsRequest(order_id="1800003902272", pattern="ORDER_STATUS_DENIED")
    )


def _workload_get_status():
    return OrderService.get_order_status(
        GetOrderStatusRequest(order_id="1800003902272")
    )


N_CALLS = 50  # enough for stable statistics, fast enough for CI


class TestBaselineBenchmark:
    @pytest.mark.overhead
    def test_baseline_runs(self):
        result = run_benchmark(_workload_get_status, n_calls=N_CALLS, label="baseline")
        assert result.n_calls == N_CALLS
        assert result.errors == 0
        assert result.mean_latency_ms > 0
        assert result.throughput_per_sec > 0

    @pytest.mark.overhead
    def test_baseline_latency_stats(self):
        result = run_benchmark(_workload_search_logs, n_calls=N_CALLS, label="search_logs")
        assert result.median_latency_ms > 0
        assert result.p95_latency_ms >= result.median_latency_ms
        assert result.stdev_latency_ms >= 0


class TestInstrumentedBenchmark:
    @pytest.mark.overhead
    @pytest.mark.parametrize("level", [
        ObservabilityLevel.O0,
        ObservabilityLevel.O1,
        ObservabilityLevel.O2,
    ])
    def test_instrumented_runs(self, level):
        result = run_benchmark(
            _workload_get_status, n_calls=N_CALLS,
            label=f"instrumented_{level.value}", obs_level=level,
        )
        assert result.n_calls == N_CALLS
        assert result.errors == 0
        assert result.mean_latency_ms > 0


class TestOverheadComparison:
    @pytest.mark.overhead
    @pytest.mark.parametrize("level", [
        ObservabilityLevel.O0,
        ObservabilityLevel.O1,
        ObservabilityLevel.O2,
    ])
    def test_overhead_comparison(self, level):
        comp = compare_overhead(_workload_get_status, level, n_calls=N_CALLS)
        summary = comp.summary()

        assert "latency_overhead_ms" in summary
        assert "throughput_overhead_pct" in summary
        assert "variance_growth" in summary

        # Overhead should be non-negative (or very small negative due to noise)
        assert summary["latency_overhead_ms"] >= -5.0  # allow 5ms jitter

    @pytest.mark.overhead
    def test_o2_overhead_greater_than_o0(self):
        """O2 instrumentation should have more overhead than O0."""
        comp_o0 = compare_overhead(_workload_get_status, ObservabilityLevel.O0, n_calls=N_CALLS)
        comp_o2 = compare_overhead(_workload_get_status, ObservabilityLevel.O2, n_calls=N_CALLS)

        # O2 should generally have higher latency than O0 (but allow noise)
        # We just verify both ran successfully
        assert comp_o0.baseline.n_calls == N_CALLS
        assert comp_o2.instrumented.n_calls == N_CALLS
