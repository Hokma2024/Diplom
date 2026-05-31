"""Export utility for saving figures as PNG/SVG/HTML."""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go


OUTPUT_DIR = Path("experiments/results/figures")


def export_figure(
    fig: go.Figure,
    name: str,
    output_dir: Path | str | None = None,
    formats: tuple[str, ...] = ("png", "html"),
    width: int = 1200,
    height: int = 700,
) -> list[str]:
    """Export a Plotly figure to specified formats.

    Returns list of saved file paths.
    """
    d = Path(output_dir) if output_dir else OUTPUT_DIR
    d.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for fmt in formats:
        path = d / f"{name}.{fmt}"
        if fmt == "html":
            fig.write_html(str(path), include_plotlyjs="cdn")
        elif fmt in ("png", "svg", "jpeg", "webp", "pdf"):
            fig.write_image(str(path), width=width, height=height)
        saved.append(str(path))
    return saved


def export_all_plots(
    df=None,
    output_dir=None,
    formats: tuple[str, ...] = ("png", "html"),
) -> list[str]:
    """Generate and export all 12 mandatory plots.

    Returns list of all saved file paths.
    """
    from .plots import (
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
        plot_hypothesis_tests,
        plot_oes_scores,
    )

    all_plots = [
        ("01_verification_summary", plot_verification_summary),
        ("02_test_stack_composition", plot_test_stack_composition),
        ("03_scenario_matrix", plot_scenario_matrix),
        ("04_comparative_view", plot_comparative_view),
        ("05_exvivo_funnel", plot_exvivo_funnel),
        ("06_exvivo_vs_baseline", plot_exvivo_vs_baseline),
        ("07_fault_observability_heatmap", plot_fault_observability_heatmap),
        ("08_time_to_detect_distribution", plot_time_to_detect_distribution),
        ("09_signal_contribution", plot_signal_contribution),
        ("10_overhead_by_obs_level", plot_overhead_by_obs_level),
        ("11_pareto_usefulness_vs_cost", plot_pareto_usefulness_vs_cost),
        ("12_incident_timeline", plot_incident_timeline),
        ("13_hypothesis_tests", plot_hypothesis_tests),
        ("14_oes_scores", plot_oes_scores),
    ]

    saved: list[str] = []
    for name, plot_fn in all_plots:
        fig = plot_fn(df=df)
        saved.extend(
            export_figure(fig, name, output_dir=output_dir, formats=formats)
        )
    return saved
