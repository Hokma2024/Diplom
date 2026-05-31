"""Block F — Performance benchmarking.

Measures overhead introduced by observability instrumentation:
- Baseline performance (no instrumentation)
- Performance under each O-level (O0, O1, O2)

Metrics collected:
- latency_ms: per-call latency
- throughput: calls/second
- resource_usage: CPU/memory deltas
- variance: standard deviation of latencies
"""

from __future__ import annotations

import statistics
import time
import resource as _resource
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from experiments.observability.configs import ObservabilityLevel, get_config
from experiments.observability.collectors import TelemetryCollector, SignalStore


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    label: str = ""
    obs_level: Optional[str] = None
    n_calls: int = 0
    total_ms: float = 0.0
    latencies_ms: List[float] = field(default_factory=list)
    errors: int = 0
    pre_rss_kb: int = 0
    post_rss_kb: int = 0

    @property
    def mean_latency_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def median_latency_ms(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def stdev_latency_ms(self) -> float:
        return statistics.stdev(self.latencies_ms) if len(self.latencies_ms) > 1 else 0.0

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_l = sorted(self.latencies_ms)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def p99_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_l = sorted(self.latencies_ms)
        idx = int(len(sorted_l) * 0.99)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def throughput_per_sec(self) -> float:
        return (self.n_calls / (self.total_ms / 1000.0)) if self.total_ms > 0 else 0.0

    @property
    def error_rate(self) -> float:
        return self.errors / self.n_calls if self.n_calls > 0 else 0.0

    @property
    def rss_delta_kb(self) -> int:
        return self.post_rss_kb - self.pre_rss_kb


@dataclass
class OverheadComparison:
    """Comparison of overhead between baseline and instrumented runs."""
    baseline: BenchmarkResult
    instrumented: BenchmarkResult

    @property
    def latency_overhead_ms(self) -> float:
        return self.instrumented.mean_latency_ms - self.baseline.mean_latency_ms

    @property
    def latency_overhead_pct(self) -> float:
        if self.baseline.mean_latency_ms > 0:
            return (self.latency_overhead_ms / self.baseline.mean_latency_ms) * 100
        return 0.0

    @property
    def throughput_overhead_pct(self) -> float:
        if self.baseline.throughput_per_sec > 0:
            delta = self.baseline.throughput_per_sec - self.instrumented.throughput_per_sec
            return (delta / self.baseline.throughput_per_sec) * 100
        return 0.0

    @property
    def variance_growth(self) -> float:
        if self.baseline.stdev_latency_ms > 0:
            return self.instrumented.stdev_latency_ms / self.baseline.stdev_latency_ms
        return 1.0

    def summary(self) -> Dict[str, Any]:
        return {
            "baseline_label": self.baseline.label,
            "instrumented_label": self.instrumented.label,
            "latency_overhead_ms": round(self.latency_overhead_ms, 3),
            "latency_overhead_pct": round(self.latency_overhead_pct, 2),
            "throughput_overhead_pct": round(self.throughput_overhead_pct, 2),
            "variance_growth": round(self.variance_growth, 2),
            "baseline_mean_ms": round(self.baseline.mean_latency_ms, 3),
            "instrumented_mean_ms": round(self.instrumented.mean_latency_ms, 3),
            "baseline_p95_ms": round(self.baseline.p95_latency_ms, 3),
            "instrumented_p95_ms": round(self.instrumented.p95_latency_ms, 3),
            "baseline_throughput": round(self.baseline.throughput_per_sec, 1),
            "instrumented_throughput": round(self.instrumented.throughput_per_sec, 1),
            "rss_delta_kb": self.instrumented.rss_delta_kb - self.baseline.rss_delta_kb,
        }


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(
    func: Callable[..., Any],
    n_calls: int = 100,
    label: str = "benchmark",
    obs_level: Optional[ObservabilityLevel] = None,
    warmup: int = 5,
) -> BenchmarkResult:
    """Run a benchmark with optional observability instrumentation.

    If obs_level is None, runs without any instrumentation (pure baseline).
    """
    # Optional instrumentation setup
    collector = None
    store = None
    if obs_level is not None:
        config = get_config(obs_level)
        store = SignalStore()
        collector = TelemetryCollector(config, store)

    # Warmup
    for _ in range(warmup):
        try:
            if collector:
                collector.instrument_call(func, call_name="warmup")
            else:
                func()
        except Exception:
            pass

    # Benchmark
    pre_rss = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    latencies: List[float] = []
    errors = 0

    if collector:
        collector.begin_trace()

    t_total_start = time.perf_counter()
    for _ in range(n_calls):
        t0 = time.perf_counter()
        try:
            if collector:
                collector.instrument_call(func, call_name=label)
            else:
                func()
        except Exception:
            errors += 1
        latencies.append((time.perf_counter() - t0) * 1000.0)
    t_total_end = time.perf_counter()

    if collector:
        collector.end_trace()

    post_rss = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss

    return BenchmarkResult(
        label=label,
        obs_level=obs_level.value if obs_level else "none",
        n_calls=n_calls,
        total_ms=(t_total_end - t_total_start) * 1000.0,
        latencies_ms=latencies,
        errors=errors,
        pre_rss_kb=pre_rss,
        post_rss_kb=post_rss,
    )


def compare_overhead(
    func: Callable[..., Any],
    obs_level: ObservabilityLevel,
    n_calls: int = 100,
    warmup: int = 5,
) -> OverheadComparison:
    """Compare baseline (no instrumentation) vs instrumented performance."""
    baseline = run_benchmark(func, n_calls=n_calls, label="baseline", warmup=warmup)
    instrumented = run_benchmark(
        func, n_calls=n_calls, label=f"instrumented_{obs_level.value}",
        obs_level=obs_level, warmup=warmup,
    )
    return OverheadComparison(baseline=baseline, instrumented=instrumented)
