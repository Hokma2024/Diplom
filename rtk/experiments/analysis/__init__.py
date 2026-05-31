"""Analysis sub-package — aggregation, statistical analysis, and OES."""

from experiments.analysis.statistics import (
    RESULTS_DIR,
    detection_rate_by_mode,
    detection_rate_by_mode_obs,
    exvivo_match_rates,
    fault_observability_heatmap_data,
    generate_diploma_tables,
    load_raw_runs,
    localization_rate_by_mode_obs,
    overhead_by_obs_level,
    regressions_by_type,
    scenario_matrix,
    signal_contribution,
    test_stack_composition,
    time_to_detect_distribution,
    time_to_localize_distribution,
    usefulness_vs_cost,
    verification_summary,
)
from experiments.analysis.hypothesis_testing import (
    run_hypothesis_tests,
    HypothesisReport,
    ProportionTestResult,
    RankTestResult,
)
from experiments.analysis.oes import (
    compute_oes_scores,
    oes_dataframe,
    oes_pareto_frontier,
    oes_sensitivity,
    OESScore,
    DEFAULT_WEIGHTS,
)

__all__ = [
    "RESULTS_DIR",
    "detection_rate_by_mode",
    "detection_rate_by_mode_obs",
    "exvivo_match_rates",
    "fault_observability_heatmap_data",
    "generate_diploma_tables",
    "load_raw_runs",
    "localization_rate_by_mode_obs",
    "overhead_by_obs_level",
    "regressions_by_type",
    "scenario_matrix",
    "signal_contribution",
    "test_stack_composition",
    "time_to_detect_distribution",
    "time_to_localize_distribution",
    "usefulness_vs_cost",
    "verification_summary",
    # Hypothesis testing
    "run_hypothesis_tests",
    "HypothesisReport",
    "ProportionTestResult",
    "RankTestResult",
    # OES
    "compute_oes_scores",
    "oes_dataframe",
    "oes_pareto_frontier",
    "oes_sensitivity",
    "OESScore",
    "DEFAULT_WEIGHTS",
]
