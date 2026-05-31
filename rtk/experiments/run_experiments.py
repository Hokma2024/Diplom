"""Experiment orchestrator — runs A0/A1/A2/A3 across all scenarios.

Iterates over every :data:`ALL_SCENARIOS` entry, applies the appropriate
experiment mode at each relevant observability level, persists
:class:`RawRunRecord` rows to ``raw_runs.jsonl``, and writes
``aggregated.csv`` via :func:`aggregate_runs`.

Usage::

    python -m experiments.run_experiments
"""

from __future__ import annotations

import copy
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.mcp_server import storage
from services.mcp_server.models import (
    CheckEissdStatusRequest,
    GetOrderStatusRequest,
    OrderStatus,
    SearchLogsRequest,
)
from services.mcp_server.services import OrderService

from experiments.data_contracts import (
    ALL_SCENARIOS,
    RawRunRecord,
    ScenarioSpec,
)
from experiments.dataset import DatasetWriter, aggregate_runs
from experiments.comparison.metrics import (
    DiagnosticMetrics,
    ExVivoMetrics,
    OverheadMetrics,
    TestingMetrics,
)
from experiments.observability.configs import (
    ObservabilityLevel,
    get_config,
)
from experiments.observability.collectors import SignalStore, TelemetryCollector
from experiments.observability.detectors import CombinedDetector
from experiments.fault_injection.faults import FaultClass, FaultSpec
from experiments.fault_injection.injector import FaultInjector
from experiments.exvivo.capture import InteractionCapture
from experiments.exvivo.replay import ReplayEngine
from experiments.overhead.benchmark import compare_overhead, run_benchmark
from experiments.shared import FAULT_CLASS_MAP, fault_params_for, service_dispatcher

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_REPEATS: int = 3
OUTPUT_DIR: str = "experiments/results"

# Snapshot pristine storage at import time so we can reset between runs.
_ORIG_LOGS_DB = copy.deepcopy(storage.LOGS_DB)
_ORIG_ORDERS_DB = copy.deepcopy(storage.ORDERS_DB)
_ORIG_EISSD_DB = copy.deepcopy(storage.EISSD_DB)
_ORIG_OTRS_TICKETS = copy.deepcopy(storage.OTRS_TICKETS)
_ORIG_OTRS_COMMENTS = copy.deepcopy(storage.OTRS_COMMENTS)


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _reset_storage() -> None:
    """Restore all in-memory mock databases to their pristine state."""
    storage.LOGS_DB.clear()
    storage.LOGS_DB.update(copy.deepcopy(_ORIG_LOGS_DB))
    storage.ORDERS_DB.clear()
    storage.ORDERS_DB.update(copy.deepcopy(_ORIG_ORDERS_DB))
    storage.EISSD_DB.clear()
    storage.EISSD_DB.update(copy.deepcopy(_ORIG_EISSD_DB))
    storage.OTRS_TICKETS.clear()
    storage.OTRS_TICKETS.update(copy.deepcopy(_ORIG_OTRS_TICKETS))
    storage.OTRS_COMMENTS.clear()
    storage.OTRS_COMMENTS.extend(copy.deepcopy(_ORIG_OTRS_COMMENTS))


def _apply_regression_mutation(scenario: ScenarioSpec) -> Dict[str, Any]:
    """Mutate in-memory storage to simulate a code regression for this scenario.

    Each regression scenario gets a distinct, realistic mutation so that
    ex-vivo replay detects a mismatch for different reasons:

    REG-001  Schema drift       — order status value changes (DENIED → IN_PROGRESS)
    REG-002  Logic change       — routing comment changes (silent business regression)
    REG-003  Boundary shift     — log entries cleared (search_logs returns no match)
    REG-004  Dead branch        — EISSD status changes (DONE instead of IN_PROGRESS)
    REG-005  Partial violation  — order status changes to FAILED

    Returns the saved values so they can be restored afterwards.
    """
    saved: Dict[str, Any] = {}
    sid = scenario.scenario_id

    if sid == "REG-001":
        saved["order_status"] = storage.ORDERS_DB["1800003902272"]["status"]
        storage.ORDERS_DB["1800003902272"]["status"] = "IN_PROGRESS"

    elif sid == "REG-002":
        saved["order_comment"] = storage.ORDERS_DB["1800003902272"]["comment"]
        storage.ORDERS_DB["1800003902272"]["comment"] = "REROUTED_BY_NEW_LOGIC"

    elif sid == "REG-003":
        saved["logs"] = list(storage.LOGS_DB.get("1800003902272", []))
        storage.LOGS_DB["1800003902272"] = []

    elif sid == "REG-004":
        saved["eissd_status"] = storage.EISSD_DB["1800003902272"]["status"]
        storage.EISSD_DB["1800003902272"]["status"] = "DONE"

    elif sid == "REG-005":
        saved["order_status"] = storage.ORDERS_DB["1800003902272"]["status"]
        storage.ORDERS_DB["1800003902272"]["status"] = "FAILED"

    return saved


def _restore_regression_mutation(scenario: ScenarioSpec, saved: Dict[str, Any]) -> None:
    """Restore storage to its pre-mutation state."""
    sid = scenario.scenario_id

    if sid in ("REG-001", "REG-005") and "order_status" in saved:
        storage.ORDERS_DB["1800003902272"]["status"] = saved["order_status"]
    elif sid == "REG-002" and "order_comment" in saved:
        storage.ORDERS_DB["1800003902272"]["comment"] = saved["order_comment"]
    elif sid == "REG-003" and "logs" in saved:
        storage.LOGS_DB["1800003902272"] = saved["logs"]
    elif sid == "REG-004" and "eissd_status" in saved:
        storage.EISSD_DB["1800003902272"]["status"] = saved["eissd_status"]


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _generate_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Baseline workload
# ---------------------------------------------------------------------------

def _run_baseline_workload() -> TestingMetrics:
    """Execute the standard 4-step baseline and return testing metrics."""
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


# ---------------------------------------------------------------------------
# Latency helper
# ---------------------------------------------------------------------------

def _measure_latency(n_calls: int = 10, warmup: int = 1) -> Dict[str, float]:
    def _workload() -> None:
        OrderService.get_order_status(GetOrderStatusRequest(order_id="1800003902272"))

    bench = run_benchmark(_workload, n_calls=n_calls, warmup=warmup, label="latency")
    return {
        "mean": bench.mean_latency_ms,
        "p95": bench.p95_latency_ms,
        "p99": bench.p99_latency_ms,
        "throughput": bench.throughput_per_sec,
        "rss_delta_kb": bench.rss_delta_kb,
    }


# ---------------------------------------------------------------------------
# Per-mode runners
# ---------------------------------------------------------------------------

def _run_a0(scenario: ScenarioSpec, repeat_idx: int, git_sha: str) -> RawRunRecord:
    """A0 — classical baseline testing only."""
    _reset_storage()
    testing = _run_baseline_workload()
    lat = _measure_latency()

    return RawRunRecord(
        run_id=_generate_run_id(),
        timestamp=_now_iso(),
        git_sha=git_sha,
        mode="A0",
        obs_level="O0",
        scenario_id=scenario.scenario_id,
        scenario_group=scenario.scenario_group,
        fault_class=scenario.fault_class,
        fault_target=scenario.fault_target,
        workload_id="baseline_4step",
        repeat_idx=repeat_idx,
        expected_detection=scenario.expected_detection,
        expected_localization=scenario.expected_localization,
        actual_detection=False,
        actual_localization=False,
        time_to_detect_ms=None,
        time_to_localize_ms=None,
        signal_types_used="",
        signal_usefulness_score=0.0,
        regressions_found=0,
        exvivo_match_rate=0.0,
        latency_mean_ms=testing.execution_time_ms,
        latency_p95_ms=lat["p95"],
        latency_p99_ms=lat["p99"],
        throughput_rps=lat["throughput"],
        variance_growth=1.0,
        resource_overhead_kb=0,
        notes=f"A0 baseline; passed={testing.passed_tests}/{testing.total_tests}",
    )


def _run_a1(scenario: ScenarioSpec, repeat_idx: int, git_sha: str) -> RawRunRecord:
    """A1 — baseline + ex-vivo regression detection.

    Workflow:
    1. Run baseline workload against pristine storage (golden state).
    2. Capture service interactions as the golden reference.
    3. Apply a scenario-specific mutation to storage (simulates a code regression).
    4. Replay captured interactions against the mutated service.
    5. Collect mismatches (regressions_found > 0 means ex-vivo detected the regression).
    6. Restore storage to pristine state.
    """
    _reset_storage()
    testing = _run_baseline_workload()

    # --- Step 1: Capture golden interactions ---
    cap = InteractionCapture()
    cap.start_scenario(f"a1_{scenario.scenario_id}")
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
    captured = cap.finish_scenario()

    # --- Step 2: Mutate storage to simulate regression ---
    saved = _apply_regression_mutation(scenario)

    # --- Step 3: Replay against mutated service ---
    engine = ReplayEngine(dispatcher=service_dispatcher)
    replay = engine.replay_scenario(captured)

    # --- Step 4: Restore storage ---
    _restore_regression_mutation(scenario, saved)

    exvivo = ExVivoMetrics(
        total_scenarios=1,
        total_interactions=replay.total_interactions,
        matched_interactions=replay.matched,
        regressions_found=replay.mismatched + replay.errors,
        replay_errors=replay.errors,
        replay_time_ms=replay.elapsed_ms,
    )

    lat = _measure_latency()

    regression_detected = exvivo.regressions_found > 0
    return RawRunRecord(
        run_id=_generate_run_id(),
        timestamp=_now_iso(),
        git_sha=git_sha,
        mode="A1",
        obs_level="O0",
        scenario_id=scenario.scenario_id,
        scenario_group=scenario.scenario_group,
        fault_class=scenario.fault_class,
        fault_target=scenario.fault_target,
        workload_id="baseline_4step+exvivo",
        repeat_idx=repeat_idx,
        expected_detection=scenario.expected_detection,
        expected_localization=scenario.expected_localization,
        actual_detection=regression_detected,
        actual_localization=regression_detected,
        time_to_detect_ms=exvivo.replay_time_ms if regression_detected else None,
        time_to_localize_ms=exvivo.replay_time_ms if regression_detected else None,
        signal_types_used="exvivo_replay" if regression_detected else "",
        signal_usefulness_score=1.0 - exvivo.match_rate if regression_detected else exvivo.match_rate,
        regressions_found=exvivo.regressions_found,
        exvivo_match_rate=exvivo.match_rate,
        latency_mean_ms=testing.execution_time_ms,
        latency_p95_ms=lat["p95"],
        latency_p99_ms=lat["p99"],
        throughput_rps=lat["throughput"],
        variance_growth=1.0,
        resource_overhead_kb=0,
        notes=(
            f"A1 exvivo; matched={replay.matched}/{replay.total_interactions} "
            f"regressions={exvivo.regressions_found} "
            f"mutation={scenario.scenario_id}"
        ),
    )


def _run_a2(
    scenario: ScenarioSpec,
    obs_level: ObservabilityLevel,
    repeat_idx: int,
    git_sha: str,
) -> RawRunRecord:
    """A2 — baseline + fault injection + observability detection.

    TTD is measured as elapsed time from the start of the fault-injection
    loop to the moment the CombinedDetector first fires (checked after
    every instrumented call).  This gives a realistic, non-zero value.

    For latency/resource/network faults the detector needs a baseline
    latency reference; we measure it with a short pre-injection benchmark.
    """
    _reset_storage()
    testing = _run_baseline_workload()

    fc: Optional[FaultClass] = FAULT_CLASS_MAP.get(scenario.fault_class)

    # Setup observability
    config = get_config(obs_level)
    store = SignalStore()
    collector = TelemetryCollector(config, store)

    # Measure baseline latency for spike detection (before injecting any fault)
    def _workload_plain() -> None:
        OrderService.get_order_status(GetOrderStatusRequest(order_id="1800003902272"))

    baseline_bench = run_benchmark(_workload_plain, n_calls=10, warmup=2, label="baseline_pre")
    baseline_lat_ms = baseline_bench.mean_latency_ms

    # Setup fault injector (skip if fc is None — signal_loss scenario)
    injector = FaultInjector()
    if fc is not None:
        injector.add_fault(
            FaultSpec(
                fault_class=fc,
                target_call="get_order_status",
                params=fault_params_for(fc),
            )
        )

    # Execute instrumented calls; detect after each one to get real TTD
    ttd_ms: Optional[float] = None
    t_inject_start = time.perf_counter()
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
                ttd_ms = (time.perf_counter() - t_inject_start) * 1000.0
    collector.end_trace()
    t_inject_elapsed = (time.perf_counter() - t_inject_start) * 1000.0

    det = CombinedDetector().detect(store, baseline_latency_ms=baseline_lat_ms)
    if ttd_ms is not None:
        det.time_to_detect_ms = ttd_ms
    elif det.detected:
        det.time_to_detect_ms = t_inject_elapsed

    diag = DiagnosticMetrics(
        fault_detected=det.detected,
        fault_localized=det.localized,
        localized_call=det.localized_call,
        time_to_detect_ms=det.time_to_detect_ms,
        signal_types_used=det.signal_types_used,
    )

    # Overhead: compare baseline vs instrumented (no fault)
    _reset_storage()
    comp = compare_overhead(_workload_plain, obs_level, n_calls=20, warmup=3)
    overhead = OverheadMetrics(
        latency_overhead_ms=comp.latency_overhead_ms,
        latency_overhead_pct=comp.latency_overhead_pct,
        throughput_overhead_pct=comp.throughput_overhead_pct,
        variance_growth=comp.variance_growth,
    )

    signal_names = ",".join(sorted(s.value for s in diag.signal_types_used))

    overhead_note = ""
    if comp.baseline.mean_latency_ms < 1.0:
        overhead_note = "; overhead_pct_unreliable=in-memory-baseline<1ms"

    return RawRunRecord(
        run_id=_generate_run_id(),
        timestamp=_now_iso(),
        git_sha=git_sha,
        mode="A2",
        obs_level=obs_level.value,
        scenario_id=scenario.scenario_id,
        scenario_group=scenario.scenario_group,
        fault_class=scenario.fault_class,
        fault_target=scenario.fault_target,
        workload_id="baseline_4step+fault+obs",
        repeat_idx=repeat_idx,
        expected_detection=scenario.expected_detection,
        expected_localization=scenario.expected_localization,
        actual_detection=det.detected,
        actual_localization=det.localized,
        time_to_detect_ms=det.time_to_detect_ms,
        time_to_localize_ms=det.time_to_detect_ms if det.localized else None,
        signal_types_used=signal_names,
        signal_usefulness_score=diag.signal_usefulness_score,
        regressions_found=0,
        exvivo_match_rate=0.0,
        latency_mean_ms=testing.execution_time_ms,
        latency_p95_ms=comp.instrumented.p95_latency_ms,
        latency_p99_ms=comp.instrumented.p99_latency_ms,
        throughput_rps=comp.instrumented.throughput_per_sec,
        variance_growth=overhead.variance_growth,
        resource_overhead_kb=comp.instrumented.rss_delta_kb,
        notes=(
            f"A2 {obs_level.value}; detected={det.detected} "
            f"localized={det.localized} "
            f"ttd={det.time_to_detect_ms:.1f}ms " if det.time_to_detect_ms is not None
            else f"A2 {obs_level.value}; detected={det.detected} "
            f"localized={det.localized} ttd=None "
        ) + f"inject_total={t_inject_elapsed:.1f}ms" + overhead_note,
    )


def _run_a3(
    scenario: ScenarioSpec,
    obs_level: ObservabilityLevel,
    repeat_idx: int,
    git_sha: str,
) -> RawRunRecord:
    """A3 — combined: ex-vivo regression + fault injection + observability."""
    _reset_storage()
    testing = _run_baseline_workload()

    # --- A1 part: capture + replay (no regression mutation for fault scenarios) ---
    cap = InteractionCapture()
    cap.start_scenario(f"a3_{scenario.scenario_id}")
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
    captured = cap.finish_scenario()
    engine = ReplayEngine(dispatcher=service_dispatcher)
    replay = engine.replay_scenario(captured)
    exvivo = ExVivoMetrics(
        total_scenarios=1,
        total_interactions=replay.total_interactions,
        matched_interactions=replay.matched,
        regressions_found=replay.mismatched + replay.errors,
        replay_errors=replay.errors,
        replay_time_ms=replay.elapsed_ms,
    )

    # --- A2 part: fault injection + observability ---
    _reset_storage()

    fc: Optional[FaultClass] = FAULT_CLASS_MAP.get(scenario.fault_class)
    config = get_config(obs_level)
    store = SignalStore()
    collector = TelemetryCollector(config, store)

    def _workload_plain() -> None:
        OrderService.get_order_status(GetOrderStatusRequest(order_id="1800003902272"))

    baseline_bench = run_benchmark(_workload_plain, n_calls=10, warmup=2, label="baseline_pre")
    baseline_lat_ms = baseline_bench.mean_latency_ms

    injector = FaultInjector()
    if fc is not None:
        injector.add_fault(
            FaultSpec(
                fault_class=fc,
                target_call="get_order_status",
                params=fault_params_for(fc),
            )
        )

    ttd_ms: Optional[float] = None
    t_inject_start = time.perf_counter()
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
                ttd_ms = (time.perf_counter() - t_inject_start) * 1000.0
    collector.end_trace()
    t_inject_elapsed = (time.perf_counter() - t_inject_start) * 1000.0

    det = CombinedDetector().detect(store, baseline_latency_ms=baseline_lat_ms)
    if ttd_ms is not None:
        det.time_to_detect_ms = ttd_ms
    elif det.detected:
        det.time_to_detect_ms = t_inject_elapsed

    diag = DiagnosticMetrics(
        fault_detected=det.detected,
        fault_localized=det.localized,
        localized_call=det.localized_call,
        time_to_detect_ms=det.time_to_detect_ms,
        signal_types_used=det.signal_types_used,
    )

    _reset_storage()
    comp = compare_overhead(_workload_plain, obs_level, n_calls=20, warmup=3)
    overhead = OverheadMetrics(
        latency_overhead_ms=comp.latency_overhead_ms,
        latency_overhead_pct=comp.latency_overhead_pct,
        throughput_overhead_pct=comp.throughput_overhead_pct,
        variance_growth=comp.variance_growth,
    )

    combined_detection = det.detected or exvivo.regressions_found > 0
    combined_localization = det.localized or exvivo.regressions_found > 0
    signal_parts = list(filter(None, ",".join(
        sorted(s.value for s in diag.signal_types_used)
    ).split(",")))
    if exvivo.regressions_found > 0 and "exvivo_replay" not in signal_parts:
        signal_parts.append("exvivo_replay")
    signal_names = ",".join(sorted(signal_parts))

    overhead_note = ""
    if comp.baseline.mean_latency_ms < 1.0:
        overhead_note = "; overhead_pct_unreliable=in-memory-baseline<1ms"

    return RawRunRecord(
        run_id=_generate_run_id(),
        timestamp=_now_iso(),
        git_sha=git_sha,
        mode="A3",
        obs_level=obs_level.value,
        scenario_id=scenario.scenario_id,
        scenario_group=scenario.scenario_group,
        fault_class=scenario.fault_class,
        fault_target=scenario.fault_target,
        workload_id="baseline_4step+exvivo+fault+obs",
        repeat_idx=repeat_idx,
        expected_detection=scenario.expected_detection,
        expected_localization=scenario.expected_localization,
        actual_detection=combined_detection,
        actual_localization=combined_localization,
        time_to_detect_ms=det.time_to_detect_ms,
        time_to_localize_ms=det.time_to_detect_ms if det.localized else None,
        signal_types_used=signal_names,
        signal_usefulness_score=diag.signal_usefulness_score,
        regressions_found=exvivo.regressions_found,
        exvivo_match_rate=exvivo.match_rate,
        latency_mean_ms=testing.execution_time_ms,
        latency_p95_ms=comp.instrumented.p95_latency_ms,
        latency_p99_ms=comp.instrumented.p99_latency_ms,
        throughput_rps=comp.instrumented.throughput_per_sec,
        variance_growth=overhead.variance_growth,
        resource_overhead_kb=comp.instrumented.rss_delta_kb,
        notes=(
            f"A3 {obs_level.value}; det={det.detected} loc={det.localized} "
            f"regr={exvivo.regressions_found} "
            + (f"ttd={det.time_to_detect_ms:.1f}ms " if det.time_to_detect_ms is not None else "ttd=None ")
            + f"inject_total={t_inject_elapsed:.1f}ms"
            + overhead_note
        ),
    )


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def _print_summary(records: List[RawRunRecord]) -> None:
    print("\n" + "=" * 72)
    print("  EXPERIMENT SUMMARY")
    print("=" * 72)
    print(f"  Total runs: {len(records)}")

    by_mode: Dict[str, List[RawRunRecord]] = {}
    for r in records:
        by_mode.setdefault(r.mode, []).append(r)

    for mode in sorted(by_mode):
        group = by_mode[mode]
        det = sum(1 for r in group if r.actual_detection)
        loc = sum(1 for r in group if r.actual_localization)
        n = len(group)
        avg_lat = sum(r.latency_mean_ms for r in group) / n if n else 0
        print(f"\n  {mode}: {n} runs")
        print(f"    Detection rate:    {det}/{n} ({det / n * 100:.0f}%)")
        print(f"    Localization rate: {loc}/{n} ({loc / n * 100:.0f}%)")
        print(f"    Avg latency:       {avg_lat:.2f} ms")

    a2_runs = by_mode.get("A2", [])
    if a2_runs:
        print("\n  A2 by observability level:")
        by_obs: Dict[str, List[RawRunRecord]] = {}
        for r in a2_runs:
            by_obs.setdefault(r.obs_level, []).append(r)
        for lvl in sorted(by_obs):
            grp = by_obs[lvl]
            det = sum(1 for r in grp if r.actual_detection)
            n = len(grp)
            print(f"    {lvl}: {det}/{n} detected ({det / n * 100:.0f}%)")

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _count_planned_runs() -> int:
    total = 0
    for sc in ALL_SCENARIOS:
        total += N_REPEATS
        if sc.scenario_group == "regression":
            total += N_REPEATS
        if sc.scenario_group == "fault":
            total += N_REPEATS * 3
            total += N_REPEATS
    return total


def _run_scenario_battery(
    sc: ScenarioSpec,
    git_sha: str,
    writer: DatasetWriter,
    all_records: List[RawRunRecord],
    counter: List[int],
    total_planned: int,
) -> None:
    def _log(mode: str, extra: str = "") -> None:
        counter[0] += 1
        label = f"  [{counter[0]}/{total_planned}] {mode}  {sc.scenario_id}"
        if extra:
            label += f" {extra}"
        print(label, flush=True)

    def _save(rec: RawRunRecord) -> None:
        writer.append_run(rec)
        all_records.append(rec)

    for rep in range(N_REPEATS):
        _log("A0", f"rep={rep}")
        _save(_run_a0(sc, repeat_idx=rep, git_sha=git_sha))

    if sc.scenario_group == "regression":
        for rep in range(N_REPEATS):
            _log("A1", f"rep={rep}")
            _save(_run_a1(sc, repeat_idx=rep, git_sha=git_sha))

    if sc.scenario_group == "fault":
        for obs in (ObservabilityLevel.O0, ObservabilityLevel.O1, ObservabilityLevel.O2):
            for rep in range(N_REPEATS):
                _log("A2", f"{obs.value} rep={rep}")
                _save(_run_a2(sc, obs_level=obs, repeat_idx=rep, git_sha=git_sha))

        for rep in range(N_REPEATS):
            _log("A3", f"O1 rep={rep}")
            _save(_run_a3(sc, obs_level=ObservabilityLevel.O1, repeat_idx=rep, git_sha=git_sha))


def main() -> None:
    git_sha = _git_sha()
    writer = DatasetWriter(output_dir=OUTPUT_DIR)

    raw_path = os.path.join(OUTPUT_DIR, "raw_runs.jsonl")
    if os.path.exists(raw_path):
        os.remove(raw_path)

    all_records: List[RawRunRecord] = []
    total_planned = _count_planned_runs()
    counter = [0]

    print(f"Experiment plan: {total_planned} runs across {len(ALL_SCENARIOS)} scenarios")
    print(f"Git SHA: {git_sha}")
    print(f"Output:  {os.path.abspath(OUTPUT_DIR)}")
    print()

    for sc in ALL_SCENARIOS:
        _run_scenario_battery(sc, git_sha, writer, all_records, counter, total_planned)

    aggregated = aggregate_runs(all_records)
    writer.write_aggregated(aggregated)

    agg_path = os.path.join(OUTPUT_DIR, "aggregated.csv")
    print(f"\nWrote {len(all_records)} raw records  → {raw_path}")
    print(f"Wrote {len(aggregated)} aggregated rows → {agg_path}")

    _print_summary(all_records)
    _reset_storage()


if __name__ == "__main__":
    main()
