"""Experiment-derived testing checklist for the RTK AI agent.

Each ChecklistItem is explicitly linked to an experiment finding.
This makes the connection between the research layer (experiments A0–A3,
LLM-specific) and the product layer (test suite) traceable and auditable.

Background problem: the 128-test A0 baseline was written before the
experiments ran, so there was no explicit link between experiment findings
and test coverage.  This module creates that link retroactively.

Usage::

    from experiments.checklists.checklist import CHECKLIST, Category
    infra = [c for c in CHECKLIST if c.category == Category.INFRASTRUCTURE]
    print_checklist(infra)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import List, Optional


class Category(str, enum.Enum):
    INFRASTRUCTURE = "infrastructure"   # from A0–A3 × O0–O2 experiments
    LLM_SPECIFIC = "llm_specific"       # from LLM-specific experiment


class ObservabilityNeeded(str, enum.Enum):
    O0 = "O0"           # error counters + health
    O1 = "O1"           # + latency + logs + traces
    O2 = "O2"           # + spans + correlation + resources
    SEMANTIC = "semantic"   # requires output-level validation — new layer


class CoverageStatus(str, enum.Enum):
    COVERED = "covered"         # test exists
    PARTIAL = "partial"         # test exists but narrow
    ADDED = "added"             # test added in this step (Шаг 4)
    MISSING = "missing"         # not yet tested


@dataclass
class ChecklistItem:
    id: str
    category: Category
    description: str
    experiment_source: str          # bug ID or LLM fault class
    observability_needed: ObservabilityNeeded
    test_ref: str                   # pytest node id or short name
    coverage: CoverageStatus
    notes: str = ""


# ---------------------------------------------------------------------------
# Infrastructure checklist  (derived from A0–A3 × O0–O2 results)
# ---------------------------------------------------------------------------

INFRA_CHECKLIST: List[ChecklistItem] = [
    ChecklistItem(
        id="CHK-I-01",
        category=Category.INFRASTRUCTURE,
        description=(
            "Время ответа get_order_status не превышает SLA (50ms) "
            "при нормальной нагрузке"
        ),
        experiment_source="BUG-007: latency spike невидима O0 → надо измерять",
        observability_needed=ObservabilityNeeded.O1,
        test_ref="test_experiment_derived::TestLatencyObservability::test_sla_order_status",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-I-02",
        category=Category.INFRASTRUCTURE,
        description=(
            "Latency spike (>3× baseline) обнаруживается на уровне O1, "
            "но не обнаруживается на уровне O0"
        ),
        experiment_source="BUG-007: ключевое различие O0 vs O1",
        observability_needed=ObservabilityNeeded.O1,
        test_ref="test_experiment_derived::TestLatencyObservability::test_o1_detects_spike_o0_does_not",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-I-03",
        category=Category.INFRASTRUCTURE,
        description=(
            "При недоступности MCP-зависимости (ConnectionError) "
            "ошибка фиксируется в action log (entry.ok=False)"
        ),
        experiment_source="BUG-006: dependency_failure обнаруживается O0",
        observability_needed=ObservabilityNeeded.O0,
        test_ref="test_experiment_derived::TestDependencyFailure::test_mcp_error_recorded_in_actions",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-I-04",
        category=Category.INFRASTRUCTURE,
        description=(
            "При таймауте MCP-зависимости (TimeoutError) "
            "final_comment содержит actions.ok=false"
        ),
        experiment_source="BUG-008: timeout обнаруживается O0",
        observability_needed=ObservabilityNeeded.O0,
        test_ref="test_experiment_derived::TestDependencyFailure::test_timeout_surfaces_in_comment",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-I-05",
        category=Category.INFRASTRUCTURE,
        description=(
            "После изменения статуса заказа (DENIED → IN_PROGRESS) "
            "get_order_status возвращает новый статус"
        ),
        experiment_source="BUG-001..005: ex-vivo регрессии при мутации данных",
        observability_needed=ObservabilityNeeded.O0,
        test_ref="test_experiment_derived::TestRegressionDetection::test_status_change_reflected",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-I-06",
        category=Category.INFRASTRUCTURE,
        description=(
            "Ex-vivo replay выявляет несоответствие при изменении "
            "статуса заказа между capture и replay"
        ),
        experiment_source="BUG-001: REG-001 schema drift",
        observability_needed=ObservabilityNeeded.O0,
        test_ref="test_experiment_derived::TestRegressionDetection::test_exvivo_detects_status_mutation",
        coverage=CoverageStatus.ADDED,
    ),
]

# ---------------------------------------------------------------------------
# LLM-specific checklist  (derived from LLM-specific experiment)
# ---------------------------------------------------------------------------

LLM_CHECKLIST: List[ChecklistItem] = [
    ChecklistItem(
        id="CHK-L-01",
        category=Category.LLM_SPECIFIC,
        description=(
            "SemanticChecker корректно определяет, "
            "что диагностические tools (get_order_status / check_eissd_status) "
            "не были вызваны"
        ),
        experiment_source="LLM_NO_TOOL_CALLS: невидим для O0/O1/O2",
        observability_needed=ObservabilityNeeded.SEMANTIC,
        test_ref="test_llm_semantic::TestSemanticChecker::test_empty_actions_fails",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-L-02",
        category=Category.LLM_SPECIFIC,
        description=(
            "Провайдер без вызовов tools (NoToolCallsProvider) "
            "не обнаруживается O0/O1/O2, но обнаруживается семантически"
        ),
        experiment_source="LLM_NO_TOOL_CALLS: главный невидимый сбой #1",
        observability_needed=ObservabilityNeeded.SEMANTIC,
        test_ref="test_llm_semantic::TestInvisibleFaults::test_no_tool_calls_invisible_to_infra",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-L-03",
        category=Category.LLM_SPECIFIC,
        description=(
            "Провайдер с неверным диагнозом (WrongDiagnosticProvider) "
            "не обнаруживается ни O0, ни O1, ни O2"
        ),
        experiment_source="LLM_WRONG_DIAGNOSTIC: главный невидимый сбой #2",
        observability_needed=ObservabilityNeeded.SEMANTIC,
        test_ref="test_llm_semantic::TestInvisibleFaults::test_wrong_diagnostic_invisible_to_all_levels",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-L-04",
        category=Category.LLM_SPECIFIC,
        description=(
            "Вызов существующего инструмента с правильными аргументами "
            "но по неверному поводу фиксируется как ok=True — "
            "без ошибки в метриках и логах"
        ),
        experiment_source="LLM_WRONG_DIAGNOSTIC: ключевое свойство невидимости",
        observability_needed=ObservabilityNeeded.SEMANTIC,
        test_ref="test_llm_semantic::TestInvisibleFaults::test_wrong_diagnostic_action_appears_ok",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-L-05",
        category=Category.LLM_SPECIFIC,
        description=(
            "Нормальный провайдер (NormalProvider) проходит "
            "семантическую проверку (get_order_status вызван успешно)"
        ),
        experiment_source="NORMAL baseline — семантика должна пропускать корректное поведение",
        observability_needed=ObservabilityNeeded.SEMANTIC,
        test_ref="test_llm_semantic::TestSemanticChecker::test_correct_tool_passes",
        coverage=CoverageStatus.ADDED,
    ),
    ChecklistItem(
        id="CHK-L-06",
        category=Category.LLM_SPECIFIC,
        description=(
            "LLM latency degradation (SlowProvider 2000ms) "
            "обнаруживается O1, но не O0 — "
            "паттерн идентичен инфраструктурному BUG-007"
        ),
        experiment_source="LLM_SLOW: методологическая согласованность с BUG-007",
        observability_needed=ObservabilityNeeded.O1,
        test_ref="test_llm_semantic::TestLLMSlowProvider::test_llm_slow_detectable_from_o1",
        coverage=CoverageStatus.ADDED,
    ),
]

# Combined full checklist
CHECKLIST: List[ChecklistItem] = INFRA_CHECKLIST + LLM_CHECKLIST


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def print_checklist(items: Optional[List[ChecklistItem]] = None) -> None:
    """Print checklist to stdout in a human-readable format."""
    items = items or CHECKLIST
    infra = [c for c in items if c.category == Category.INFRASTRUCTURE]
    llm = [c for c in items if c.category == Category.LLM_SPECIFIC]

    print()
    print("=" * 72)
    print("  RTK Agent — Testing Checklist (experiment-derived)")
    print("=" * 72)

    for group_name, group in [("Infrastructure (A0–A3 × O0–O2)", infra),
                               ("LLM-specific (LLM experiment)", llm)]:
        if not group:
            continue
        print(f"\n  [{group_name}]")
        print(f"  {'ID':<10} {'Obs':<10} {'Cov':<8} Description")
        print(f"  {'-'*10} {'-'*10} {'-'*8} {'-'*42}")
        for item in group:
            status_icon = {"covered": "✓", "partial": "~", "added": "+", "missing": "✗"}.get(
                item.coverage.value, "?"
            )
            print(
                f"  {item.id:<10} {item.observability_needed.value:<10} "
                f"{status_icon} {item.coverage.value:<6}  {item.description[:60]}"
            )
            print(f"  {'':10} {'':10} {'':8} ← {item.experiment_source}")
        print()

    added = sum(1 for c in items if c.coverage == CoverageStatus.ADDED)
    covered = sum(1 for c in items if c.coverage == CoverageStatus.COVERED)
    missing = sum(1 for c in items if c.coverage == CoverageStatus.MISSING)
    print(f"  Total: {len(items)} items  |  + added={added}  ✓ pre-existing={covered}  ✗ missing={missing}")
    print()
