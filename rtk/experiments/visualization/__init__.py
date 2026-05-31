"""Visualization sub-package — 12 mandatory scientific plots + export helpers."""

from experiments.visualization.plots import (
    plot_verification_summary,
    plot_test_stack_composition,
    plot_scenario_matrix,
    plot_comparative_view,
    plot_exvivo_funnel,
    plot_exvivo_vs_baseline,
    plot_fault_observability_heatmap,
    plot_time_to_detect_distribution,
    plot_signal_contribution,
    plot_overhead_by_obs_level,
    plot_pareto_usefulness_vs_cost,
    plot_incident_timeline,
)
from experiments.visualization.export import export_figure, export_all_plots

__all__ = [
    "plot_verification_summary",
    "plot_test_stack_composition",
    "plot_scenario_matrix",
    "plot_comparative_view",
    "plot_exvivo_funnel",
    "plot_exvivo_vs_baseline",
    "plot_fault_observability_heatmap",
    "plot_time_to_detect_distribution",
    "plot_signal_contribution",
    "plot_overhead_by_obs_level",
    "plot_pareto_usefulness_vs_cost",
    "plot_incident_timeline",
    "export_figure",
    "export_all_plots",
]
