"""Data contracts for the experimental dataset.

Defines the canonical schemas used across all experiment runs, aggregation
pipelines, and reporting modules.  Every raw CSV / JSON row produced by the
runner is validated against :class:`RawRunRecord`; downstream analytics
consume :class:`AggregatedResult`.

# Контракты данных экспериментального датасета.
# RawRunRecord  — одна строка «сырых» результатов прогона.
# AggregatedResult — агрегированный итог по группе прогонов.
# ScenarioSpec — спецификация одного сценария эксперимента.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Контракт: запись одного прогона (raw run)
# ---------------------------------------------------------------------------

@dataclass
class RawRunRecord:
    """Single experiment run as persisted in the raw dataset."""

    run_id: str
    timestamp: str                   # ISO-8601
    git_sha: str
    mode: str                        # A0 / A1 / A2 / A3
    obs_level: str                   # O0 / O1 / O2
    scenario_id: str
    scenario_group: str              # regression / fault / baseline
    fault_class: str
    fault_target: str
    workload_id: str
    repeat_idx: int
    expected_detection: bool
    expected_localization: bool
    actual_detection: bool
    actual_localization: bool
    time_to_detect_ms: Optional[float]
    time_to_localize_ms: Optional[float]
    signal_types_used: str           # comma-separated signal names
    signal_usefulness_score: float
    regressions_found: int
    exvivo_match_rate: float
    latency_mean_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    throughput_rps: float
    variance_growth: float
    resource_overhead_kb: int
    notes: str


# ---------------------------------------------------------------------------
# Контракт: агрегированный результат по группе прогонов
# ---------------------------------------------------------------------------

@dataclass
class AggregatedResult:
    """Aggregated metrics computed over a group of runs."""

    mode: str
    obs_level: str
    scenario_group: str
    total_runs: int
    detection_rate: float
    localization_rate: float
    mean_time_to_detect_ms: float
    mean_time_to_localize_ms: float
    mean_signal_usefulness: float
    total_regressions_found: int
    mean_exvivo_match_rate: float
    mean_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    mean_throughput_rps: float
    mean_variance_growth: float
    mean_overhead_kb: float
    ci_detection_lower: float        # 95 % CI lower bound
    ci_detection_upper: float        # 95 % CI upper bound


# ---------------------------------------------------------------------------
# Контракт: спецификация сценария
# ---------------------------------------------------------------------------

@dataclass
class ScenarioSpec:
    """Specification of a single experiment scenario."""

    scenario_id: str
    scenario_group: str              # regression / fault / baseline
    name: str
    description: str
    fault_class: str
    fault_target: str
    expected_detection: bool
    expected_localization: bool
    expected_strongest_mode: str     # A0 … A3
    relevant_signals: List[str] = field(default_factory=list)
    relevant_visualizations: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Утилиты сериализации
# ---------------------------------------------------------------------------

def to_dict(record: RawRunRecord) -> Dict[str, Any]:
    """Convert a :class:`RawRunRecord` to a plain dictionary."""
    return asdict(record)


def from_dict(d: Dict[str, Any]) -> RawRunRecord:
    """Construct a :class:`RawRunRecord` from a plain dictionary."""
    return RawRunRecord(**d)


# ---------------------------------------------------------------------------
# Каталог сценариев: регрессионные (REG-*)
# ---------------------------------------------------------------------------

REGRESSION_SCENARIOS: List[ScenarioSpec] = [
    ScenarioSpec(
        scenario_id="REG-001",
        scenario_group="regression",
        name="Incompatible response structure change",
        description=(
            "A provider returns a restructured JSON payload that breaks "
            "downstream field mapping."
        ),
        fault_class="schema_drift",
        fault_target="provider_response",
        expected_detection=True,
        expected_localization=True,
        expected_strongest_mode="A3",
        relevant_signals=["schema_diff", "field_mapping_error", "contract_violation"],
        relevant_visualizations=["diff_heatmap", "timeline"],
    ),
    ScenarioSpec(
        scenario_id="REG-002",
        scenario_group="regression",
        name="Hidden business regression",
        description=(
            "Logic change causes silently incorrect order routing that is "
            "only visible through business-metric drift."
        ),
        fault_class="logic_change",
        fault_target="routing_logic",
        expected_detection=True,
        expected_localization=False,
        expected_strongest_mode="A2",
        relevant_signals=["metric_drift", "routing_ratio", "business_kpi"],
        relevant_visualizations=["kpi_dashboard", "drift_chart"],
    ),
    ScenarioSpec(
        scenario_id="REG-003",
        scenario_group="regression",
        name="Edge-case behavior change",
        description=(
            "Boundary input that previously succeeded now triggers a "
            "validation error after a library update."
        ),
        fault_class="boundary_shift",
        fault_target="input_validation",
        expected_detection=True,
        expected_localization=True,
        expected_strongest_mode="A3",
        relevant_signals=["error_rate", "validation_log", "boundary_trace"],
        relevant_visualizations=["error_histogram", "trace_waterfall"],
    ),
    ScenarioSpec(
        scenario_id="REG-004",
        scenario_group="regression",
        name="Pipeline branch break",
        description=(
            "A conditional branch in the processing pipeline silently "
            "becomes unreachable after a refactor."
        ),
        fault_class="dead_branch",
        fault_target="pipeline_branch",
        expected_detection=True,
        expected_localization=True,
        expected_strongest_mode="A3",
        relevant_signals=["coverage_delta", "branch_hit_count", "path_trace"],
        relevant_visualizations=["coverage_map", "branch_flow"],
    ),
    ScenarioSpec(
        scenario_id="REG-005",
        scenario_group="regression",
        name="Partial contract violation",
        description=(
            "Only a subset of response fields violate the contract, "
            "leaving overall structure intact but values incorrect."
        ),
        fault_class="partial_violation",
        fault_target="response_fields",
        expected_detection=True,
        expected_localization=True,
        expected_strongest_mode="A3",
        relevant_signals=["field_value_check", "contract_violation", "anomaly_score"],
        relevant_visualizations=["field_diff_table", "anomaly_chart"],
    ),
]


# ---------------------------------------------------------------------------
# Каталог сценариев: инъекция неисправностей (FLT-*)
# ---------------------------------------------------------------------------

FAULT_SCENARIOS: List[ScenarioSpec] = [
    ScenarioSpec(
        scenario_id="FLT-001",
        scenario_group="fault",
        name="Latency injection",
        description="Artificial delay added to a target service endpoint.",
        fault_class="latency",
        fault_target="service_endpoint",
        expected_detection=True,
        expected_localization=True,
        expected_strongest_mode="A2",
        relevant_signals=["latency_histogram", "p99_spike", "trace_duration"],
        relevant_visualizations=["latency_heatmap", "trace_waterfall"],
    ),
    ScenarioSpec(
        scenario_id="FLT-002",
        scenario_group="fault",
        name="Timeout",
        description="Target service exceeds the configured timeout threshold.",
        fault_class="timeout",
        fault_target="service_endpoint",
        expected_detection=True,
        expected_localization=True,
        expected_strongest_mode="A2",
        relevant_signals=["timeout_count", "error_rate", "circuit_state"],
        relevant_visualizations=["error_timeline", "circuit_breaker_chart"],
    ),
    ScenarioSpec(
        scenario_id="FLT-003",
        scenario_group="fault",
        name="Dependency failure",
        description="An external dependency becomes completely unavailable.",
        fault_class="dependency_down",
        fault_target="external_dependency",
        expected_detection=True,
        expected_localization=True,
        expected_strongest_mode="A1",
        relevant_signals=["error_rate", "dependency_health", "fallback_trigger"],
        relevant_visualizations=["dependency_map", "error_timeline"],
    ),
    ScenarioSpec(
        scenario_id="FLT-004",
        scenario_group="fault",
        name="Partial unavailability",
        description=(
            "One replica of a service is down while others remain healthy."
        ),
        fault_class="partial_outage",
        fault_target="service_replica",
        expected_detection=True,
        expected_localization=False,
        expected_strongest_mode="A2",
        relevant_signals=["instance_health", "error_rate_per_pod", "load_balance_skew"],
        relevant_visualizations=["replica_grid", "error_rate_chart"],
    ),
    ScenarioSpec(
        scenario_id="FLT-005",
        scenario_group="fault",
        name="Resource degradation",
        description="CPU or memory pressure causes throughput degradation.",
        fault_class="resource_pressure",
        fault_target="compute_resource",
        expected_detection=True,
        expected_localization=True,
        expected_strongest_mode="A2",
        relevant_signals=["cpu_usage", "memory_usage", "throughput_drop"],
        relevant_visualizations=["resource_gauge", "throughput_chart"],
    ),
    ScenarioSpec(
        scenario_id="FLT-006",
        scenario_group="fault",
        name="Network degradation",
        description="Packet loss or bandwidth limitation between services.",
        fault_class="network_fault",
        fault_target="network_link",
        expected_detection=True,
        expected_localization=False,
        expected_strongest_mode="A2",
        relevant_signals=["retransmit_rate", "latency_variance", "packet_loss"],
        relevant_visualizations=["network_topology", "latency_scatter"],
    ),
    ScenarioSpec(
        scenario_id="FLT-007",
        scenario_group="fault",
        name="Correlation loss",
        description=(
            "Trace context propagation breaks, losing cross-service "
            "correlation."
        ),
        fault_class="correlation_break",
        fault_target="trace_context",
        expected_detection=True,
        expected_localization=False,
        expected_strongest_mode="A3",
        relevant_signals=["orphan_span_rate", "trace_completeness", "correlation_id_miss"],
        relevant_visualizations=["trace_graph", "correlation_matrix"],
    ),
    ScenarioSpec(
        scenario_id="FLT-008",
        scenario_group="fault",
        name="Signal sparsity",
        description=(
            "Telemetry collection is degraded, producing sparse signals "
            "that complicate root-cause analysis."
        ),
        fault_class="signal_loss",
        fault_target="telemetry_pipeline",
        expected_detection=False,
        expected_localization=False,
        expected_strongest_mode="A3",
        relevant_signals=["signal_density", "collection_gap", "ingestion_lag"],
        relevant_visualizations=["signal_coverage_map", "gap_timeline"],
    ),
]


# ---------------------------------------------------------------------------
# Каталог сценариев: базовые / нормальные (BAS-*)
# ---------------------------------------------------------------------------

BASELINE_SCENARIOS: List[ScenarioSpec] = [
    ScenarioSpec(
        scenario_id="BAS-001",
        scenario_group="baseline",
        name="Normal order processing",
        description="Standard order flow with no injected faults.",
        fault_class="none",
        fault_target="none",
        expected_detection=False,
        expected_localization=False,
        expected_strongest_mode="A0",
        relevant_signals=["latency_histogram", "throughput", "error_rate"],
        relevant_visualizations=["dashboard_overview"],
    ),
    ScenarioSpec(
        scenario_id="BAS-002",
        scenario_group="baseline",
        name="Denied order handling",
        description="Order is denied by business rules; no fault expected.",
        fault_class="none",
        fault_target="none",
        expected_detection=False,
        expected_localization=False,
        expected_strongest_mode="A0",
        relevant_signals=["denial_count", "error_rate", "latency_histogram"],
        relevant_visualizations=["denial_funnel"],
    ),
    ScenarioSpec(
        scenario_id="BAS-003",
        scenario_group="baseline",
        name="Missing order error handling",
        description="Request references a non-existent order; expected 404.",
        fault_class="none",
        fault_target="none",
        expected_detection=False,
        expected_localization=False,
        expected_strongest_mode="A0",
        relevant_signals=["http_status_count", "error_rate", "latency_histogram"],
        relevant_visualizations=["status_code_pie"],
    ),
]


# Объединённый список всех сценариев
ALL_SCENARIOS: List[ScenarioSpec] = (
    BASELINE_SCENARIOS + REGRESSION_SCENARIOS + FAULT_SCENARIOS
)
