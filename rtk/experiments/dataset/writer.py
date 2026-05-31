"""Dataset writer — persists raw runs (JSONL) and aggregated results (CSV).

Provides :class:`DatasetWriter` for file I/O and :func:`aggregate_runs` for
computing group-level statistics from a list of :class:`RawRunRecord`.

# Модуль записи датасета — сохраняет «сырые» прогоны (JSONL) и
# агрегированные результаты (CSV).
"""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
from dataclasses import asdict, fields
from itertools import groupby
from typing import Dict, List

from experiments.data_contracts import AggregatedResult, RawRunRecord, from_dict, to_dict


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class DatasetWriter:
    """Append raw run records to JSONL and write aggregated results to CSV."""

    _RAW_FILENAME = "raw_runs.jsonl"
    _AGG_FILENAME = "aggregated.csv"

    def __init__(self, output_dir: str = "experiments/results") -> None:
        self._output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    # -- raw runs -----------------------------------------------------------

    def append_run(self, record: RawRunRecord) -> None:
        """Append a single run record to ``raw_runs.jsonl``."""
        path = os.path.join(self._output_dir, self._RAW_FILENAME)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(to_dict(record), ensure_ascii=False) + "\n")

    def load_raw_runs(self) -> List[RawRunRecord]:
        """Load all raw run records from ``raw_runs.jsonl``."""
        path = os.path.join(self._output_dir, self._RAW_FILENAME)
        if not os.path.exists(path):
            return []
        runs: List[RawRunRecord] = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    runs.append(from_dict(json.loads(line)))
        return runs

    # -- aggregated results -------------------------------------------------

    def write_aggregated(self, results: List[AggregatedResult]) -> None:
        """Write aggregated results to ``aggregated.csv`` with headers."""
        path = os.path.join(self._output_dir, self._AGG_FILENAME)
        if not results:
            return
        fieldnames = [f.name for f in fields(AggregatedResult)]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for result in results:
                writer.writerow(asdict(result))

    def load_aggregated(self) -> List[Dict[str, str]]:
        """Load aggregated results from ``aggregated.csv``."""
        path = os.path.join(self._output_dir, self._AGG_FILENAME)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Aggregation logic
# ---------------------------------------------------------------------------

def _safe_mean(values: List[float]) -> float:
    """Return the arithmetic mean or 0.0 when the list is empty."""
    return statistics.mean(values) if values else 0.0


def _safe_quantile(values: List[float], q: float) -> float:
    """Return a quantile value or 0.0 when the list is empty."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = q * (len(sorted_vals) - 1)
    lower = int(math.floor(idx))
    upper = int(math.ceil(idx))
    if lower == upper:
        return sorted_vals[lower]
    frac = idx - lower
    return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac


def _group_key(r: RawRunRecord) -> tuple[str, str, str]:
    return (r.mode, r.obs_level, r.scenario_group)


def aggregate_runs(runs: List[RawRunRecord]) -> List[AggregatedResult]:
    """Group runs by (mode, obs_level, scenario_group) and compute stats.

    Returns a list of :class:`AggregatedResult`, one entry per group.
    """
    if not runs:
        return []

    sorted_runs = sorted(runs, key=_group_key)
    results: List[AggregatedResult] = []

    for key, group_iter in groupby(sorted_runs, key=_group_key):
        group: List[RawRunRecord] = list(group_iter)
        mode, obs_level, scenario_group = key
        n = len(group)

        # Detection / localisation rates
        det_count = sum(1 for r in group if r.actual_detection)
        loc_count = sum(1 for r in group if r.actual_localization)
        detection_rate = det_count / n
        localization_rate = loc_count / n

        # Timing (only where a value was recorded)
        detect_times = [
            r.time_to_detect_ms for r in group if r.time_to_detect_ms is not None
        ]
        localize_times = [
            r.time_to_localize_ms for r in group if r.time_to_localize_ms is not None
        ]

        # Signal / regression / exvivo
        mean_signal = _safe_mean([r.signal_usefulness_score for r in group])
        total_regressions = sum(r.regressions_found for r in group)
        mean_exvivo = _safe_mean([r.exvivo_match_rate for r in group])

        # Latency stats
        latencies = [r.latency_mean_ms for r in group]
        p95_vals = [r.latency_p95_ms for r in group]
        p99_vals = [r.latency_p99_ms for r in group]

        # Throughput, variance, overhead
        mean_throughput = _safe_mean([r.throughput_rps for r in group])
        mean_variance = _safe_mean([r.variance_growth for r in group])
        mean_overhead = _safe_mean([float(r.resource_overhead_kb) for r in group])

        # 95 % confidence interval for detection_rate: p ± 1.96*sqrt(p(1-p)/n)
        p = detection_rate
        if n > 0:
            se = math.sqrt(p * (1 - p) / n)
        else:
            se = 0.0
        ci_lower = max(0.0, p - 1.96 * se)
        ci_upper = min(1.0, p + 1.96 * se)

        results.append(
            AggregatedResult(
                mode=mode,
                obs_level=obs_level,
                scenario_group=scenario_group,
                total_runs=n,
                detection_rate=round(detection_rate, 6),
                localization_rate=round(localization_rate, 6),
                mean_time_to_detect_ms=round(_safe_mean(detect_times), 3),
                mean_time_to_localize_ms=round(_safe_mean(localize_times), 3),
                mean_signal_usefulness=round(mean_signal, 6),
                total_regressions_found=total_regressions,
                mean_exvivo_match_rate=round(mean_exvivo, 6),
                mean_latency_ms=round(_safe_mean(latencies), 3),
                p95_latency_ms=round(_safe_quantile(p95_vals, 0.95), 3),
                p99_latency_ms=round(_safe_quantile(p99_vals, 0.99), 3),
                mean_throughput_rps=round(mean_throughput, 3),
                mean_variance_growth=round(mean_variance, 6),
                mean_overhead_kb=round(mean_overhead, 3),
                ci_detection_lower=round(ci_lower, 6),
                ci_detection_upper=round(ci_upper, 6),
            )
        )

    return results
