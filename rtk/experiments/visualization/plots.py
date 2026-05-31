"""Visualization module — 12 mandatory scientific plots.

Uses Plotly for all visualizations. Each function returns a plotly Figure.
Figures can be exported as PNG/SVG/HTML.
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd

from experiments.analysis.statistics import (
    load_raw_runs,
    detection_rate_by_mode,
    detection_rate_by_mode_obs,
    localization_rate_by_mode_obs,
    time_to_detect_distribution,
    time_to_localize_distribution,
    exvivo_match_rates,
    regressions_by_type,
    fault_observability_heatmap_data,
    overhead_by_obs_level,
    signal_contribution,
    usefulness_vs_cost,
    scenario_matrix,
    verification_summary,
    test_stack_composition,
)

# ---------------------------------------------------------------------------
# Consistent color palette
# ---------------------------------------------------------------------------
MODE_COLORS: dict[str, str] = {
    "A0": "#636EFA",
    "A1": "#EF553B",
    "A2": "#00CC96",
    "A3": "#AB63FA",
}

OBS_COLORS: dict[str, str] = {
    "O0": "#FFA15A",
    "O1": "#19D3F3",
    "O2": "#FF6692",
}

GROUP_COLORS: dict[str, str] = {
    "baseline": "#636EFA",
    "regression": "#EF553B",
    "fault": "#00CC96",
}

_TEMPLATE = "plotly_white"


def _ensure_df(df: pd.DataFrame | None) -> pd.DataFrame:
    """Load raw runs from file when *df* is not supplied."""
    if df is None:
        return load_raw_runs()
    return df


# ======================================================================
# 1. Verification Summary
# ======================================================================

def plot_verification_summary(df: pd.DataFrame | None = None) -> go.Figure:
    """Indicator / summary card showing key verification metrics."""
    df = _ensure_df(df)
    info = verification_summary(df)

    total_runs = info["total_runs"]
    n_scenarios = len(info["scenarios"])
    n_modes = len(info["modes"])
    n_obs = len(info["obs_levels"])
    det_total = info["detection_pass"] + info["detection_fail"]
    pass_rate = info["detection_pass"] / det_total if det_total else 0

    fig = make_subplots(
        rows=2,
        cols=3,
        specs=[[{"type": "indicator"}] * 3, [{"type": "indicator"}] * 3],
        vertical_spacing=0.25,
        horizontal_spacing=0.15,
    )

    indicators = [
        ("Total Runs", total_runs, None, 1, 1),
        ("Scenarios", n_scenarios, None, 1, 2),
        ("Detection Pass Rate", pass_rate, ".1%", 1, 3),
        ("Modes Covered", n_modes, None, 2, 1),
        ("Observability Levels", n_obs, None, 2, 2),
        ("Localization Passes", info["localization_pass"], None, 2, 3),
    ]

    for title, value, fmt, row, col in indicators:
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=value,
                title={"text": title, "font": {"size": 16}},
                number={"font": {"size": 36}, "valueformat": fmt or ","},
            ),
            row=row,
            col=col,
        )

    fig.update_layout(
        template=_TEMPLATE,
        title_text="Verification Summary",
        title_x=0.5,
        height=450,
    )
    return fig


# ======================================================================
# 2. Test Stack Composition
# ======================================================================

def plot_test_stack_composition(df: pd.DataFrame | None = None) -> go.Figure:
    """Stacked bar chart: x=mode, y=count, colour=scenario_group."""
    df = _ensure_df(df)

    if df.empty:
        return _empty_figure("Test Stack Composition")

    comp = (
        df.groupby(["mode", "scenario_group"])
        .size()
        .reset_index(name="count")
    )

    mode_order = sorted(comp["mode"].unique())
    groups = sorted(comp["scenario_group"].unique())

    fig = go.Figure()
    for grp in groups:
        sub = comp[comp["scenario_group"] == grp]
        fig.add_trace(
            go.Bar(
                x=sub["mode"],
                y=sub["count"],
                name=grp.capitalize(),
                marker_color=GROUP_COLORS.get(grp, "#999999"),
            )
        )

    fig.update_layout(
        barmode="stack",
        template=_TEMPLATE,
        title_text="Test Stack Composition by Mode",
        title_x=0.5,
        xaxis_title="Mode",
        yaxis_title="Number of Runs",
        xaxis={"categoryorder": "array", "categoryarray": mode_order},
        legend_title_text="Scenario Group",
    )
    return fig


# ======================================================================
# 3. Scenario Matrix
# ======================================================================

def plot_scenario_matrix(df: pd.DataFrame | None = None) -> go.Figure:
    """Heatmap: rows=scenario_id, columns=mode, values=detection_rate."""
    df = _ensure_df(df)
    pivot = scenario_matrix(df)

    if pivot.empty:
        return _empty_figure("Scenario Detection Matrix")

    mode_order = [m for m in ["A0", "A1", "A2", "A3"] if m in pivot.columns]
    pivot = pivot[mode_order]

    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale="RdYlGn",
            zmin=0,
            zmax=1,
            text=[[f"{v:.0%}" if pd.notna(v) else "" for v in row] for row in pivot.values],
            texttemplate="%{text}",
            textfont={"size": 11},
            colorbar_title="Detection Rate",
        )
    )
    fig.update_layout(
        template=_TEMPLATE,
        title_text="Scenario × Mode Detection Matrix",
        title_x=0.5,
        xaxis_title="Mode",
        yaxis_title="Scenario",
        yaxis_autorange="reversed",
        height=max(400, 30 * len(pivot) + 150),
    )
    return fig


# ======================================================================
# 4. Comparative View
# ======================================================================

def plot_comparative_view(df: pd.DataFrame | None = None) -> go.Figure:
    """Grouped bar chart comparing modes on key metrics."""
    df = _ensure_df(df)

    if df.empty:
        return _empty_figure("Comparative View")

    det = detection_rate_by_mode(df)
    loc = localization_rate_by_mode_obs(df)
    modes = sorted(df["mode"].unique())

    # Build per-mode metric rows
    rows: list[dict] = []
    for mode in modes:
        d_rate = det.loc[det["mode"] == mode, "detection_rate"]
        d_val = float(d_rate.iloc[0]) if len(d_rate) else 0.0

        l_sub = loc[loc["mode"] == mode]
        l_val = float(l_sub["localization_rate"].mean()) if not l_sub.empty else 0.0

        u_sub = df[df["mode"] == mode]["signal_usefulness_score"]
        u_val = float(u_sub.mean()) if not u_sub.empty else 0.0

        rows.append({
            "mode": mode,
            "Detection Rate": d_val,
            "Localization Rate": l_val,
            "Signal Usefulness": u_val,
        })

    mdf = pd.DataFrame(rows)

    fig = go.Figure()
    for metric in ["Detection Rate", "Localization Rate", "Signal Usefulness"]:
        fig.add_trace(
            go.Bar(
                x=mdf["mode"],
                y=mdf[metric],
                name=metric,
            )
        )

    fig.update_layout(
        barmode="group",
        template=_TEMPLATE,
        title_text="Comparative View: Modes × Key Metrics",
        title_x=0.5,
        xaxis_title="Mode",
        yaxis_title="Score",
        yaxis_range=[0, 1.05],
        legend_title_text="Metric",
        xaxis={"categoryorder": "array", "categoryarray": modes},
    )
    return fig


# ======================================================================
# 5. Ex-Vivo Funnel
# ======================================================================

def plot_exvivo_funnel(df: pd.DataFrame | None = None) -> go.Figure:
    """Funnel chart: Total Interactions → Matched → Regressions Found."""
    df = _ensure_df(df)
    exvivo = df[df["mode"].isin(["A1", "A3"])].copy()

    if exvivo.empty:
        return _empty_figure("Ex-Vivo Funnel")

    total = len(exvivo)
    matched = int((exvivo["exvivo_match_rate"] > 0).sum())
    regressions = int((exvivo["regressions_found"] > 0).sum())

    fig = go.Figure(
        go.Funnel(
            y=["Total Interactions", "Matched (rate > 0)", "Regressions Found"],
            x=[total, matched, regressions],
            textinfo="value+percent initial",
            marker_color=["#636EFA", "#00CC96", "#EF553B"],
        )
    )
    fig.update_layout(
        template=_TEMPLATE,
        title_text="Ex-Vivo Analysis Funnel (A1 & A3 Modes)",
        title_x=0.5,
    )
    return fig


# ======================================================================
# 6. Ex-Vivo vs Baseline
# ======================================================================

def plot_exvivo_vs_baseline(df: pd.DataFrame | None = None) -> go.Figure:
    """Grouped bar: regressions found per regression scenario, A0 vs A1."""
    df = _ensure_df(df)
    reg = regressions_by_type(df)

    if reg.empty:
        return _empty_figure("Ex-Vivo vs Baseline Regressions")

    compare_modes = [m for m in ["A0", "A1"] if m in reg["mode"].values]
    reg_sub = reg[reg["mode"].isin(compare_modes)]
    scenarios = sorted(reg_sub["scenario_id"].unique())

    fig = go.Figure()
    for mode in compare_modes:
        sub = reg_sub[reg_sub["mode"] == mode]
        fig.add_trace(
            go.Bar(
                x=sub["scenario_id"],
                y=sub["total_regressions"],
                name=mode,
                marker_color=MODE_COLORS.get(mode, "#999999"),
            )
        )

    fig.update_layout(
        barmode="group",
        template=_TEMPLATE,
        title_text="Regressions Found: A0 (Baseline) vs A1 (Ex-Vivo)",
        title_x=0.5,
        xaxis_title="Regression Scenario",
        yaxis_title="Total Regressions Found",
        xaxis={"categoryorder": "array", "categoryarray": scenarios},
        legend_title_text="Mode",
    )
    return fig


# ======================================================================
# 7. Fault Observability Heatmap
# ======================================================================

def plot_fault_observability_heatmap(
    df: pd.DataFrame | None = None,
) -> go.Figure:
    """Heatmap: fault scenario × obs_level → detection rate."""
    df = _ensure_df(df)
    pivot = fault_observability_heatmap_data(df)

    if pivot.empty:
        return _empty_figure("Fault Observability Heatmap")

    obs_order = [o for o in ["O0", "O1", "O2"] if o in pivot.columns]
    pivot = pivot[obs_order]

    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale="RdYlGn",
            zmin=0,
            zmax=1,
            text=[
                [f"{v:.0%}" if pd.notna(v) else "" for v in row]
                for row in pivot.values
            ],
            texttemplate="%{text}",
            textfont={"size": 12},
            colorbar_title="Detection Rate",
        )
    )
    fig.update_layout(
        template=_TEMPLATE,
        title_text="Fault Detection Rate by Scenario × Observability Level",
        title_x=0.5,
        xaxis_title="Observability Level",
        yaxis_title="Fault Scenario",
        yaxis_autorange="reversed",
        height=max(400, 40 * len(pivot) + 150),
    )
    return fig


# ======================================================================
# 8. Time-to-Detect Distribution (box plot)
# ======================================================================

def plot_time_to_detect_distribution(
    df: pd.DataFrame | None = None,
) -> go.Figure:
    """Box plot: time_to_detect_ms by mode + obs_level."""
    df = _ensure_df(df)

    detected = df[df["actual_detection"].astype(bool)].copy()
    if detected.empty or "time_to_detect_ms" not in detected.columns:
        return _empty_figure("Time-to-Detect Distribution")

    detected = detected.dropna(subset=["time_to_detect_ms"])
    detected["group"] = detected["mode"] + " / " + detected["obs_level"]

    group_order = sorted(detected["group"].unique())

    fig = go.Figure()
    for grp in group_order:
        sub = detected[detected["group"] == grp]
        mode = sub["mode"].iloc[0]
        fig.add_trace(
            go.Box(
                y=sub["time_to_detect_ms"],
                name=grp,
                marker_color=MODE_COLORS.get(mode, "#999999"),
                boxmean="sd",
            )
        )

    fig.update_layout(
        template=_TEMPLATE,
        title_text="Time-to-Detect Distribution by Mode / Obs Level",
        title_x=0.5,
        yaxis_title="Time to Detect (ms)",
        xaxis_title="Mode / Observability Level",
        showlegend=False,
    )
    return fig


# ======================================================================
# 9. Signal Contribution
# ======================================================================

def plot_signal_contribution(df: pd.DataFrame | None = None) -> go.Figure:
    """Horizontal bar chart of signal type usage frequency."""
    df = _ensure_df(df)
    sig = signal_contribution(df)

    if sig.empty:
        return _empty_figure("Signal Contribution")

    sig = sig.sort_values("count", ascending=True)

    fig = go.Figure(
        go.Bar(
            x=sig["count"],
            y=sig["signal_type"],
            orientation="h",
            marker_color="#636EFA",
            text=sig["count"],
            textposition="outside",
        )
    )
    fig.update_layout(
        template=_TEMPLATE,
        title_text="Signal Type Contribution (Usage Frequency)",
        title_x=0.5,
        xaxis_title="Count",
        yaxis_title="Signal Type",
        height=max(350, 50 * len(sig) + 100),
    )
    return fig


# ======================================================================
# 10. Overhead by Observability Level
# ======================================================================

def plot_overhead_by_obs_level(df: pd.DataFrame | None = None) -> go.Figure:
    """Multi-axis line chart: latency and resource overhead vs obs level."""
    df = _ensure_df(df)
    oh = overhead_by_obs_level(df)

    if oh.empty:
        return _empty_figure("Overhead by Observability Level")

    obs_order = [o for o in ["O0", "O1", "O2"] if o in oh["obs_level"].values]
    oh = oh.set_index("obs_level").loc[obs_order].reset_index()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=oh["obs_level"],
            y=oh["latency_mean_ms"],
            mode="lines+markers",
            name="Latency (ms)",
            marker=dict(size=10, color=OBS_COLORS["O1"]),
            line=dict(width=2.5),
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=oh["obs_level"],
            y=oh["resource_overhead_kb"],
            mode="lines+markers",
            name="Resource Overhead (KB)",
            marker=dict(size=10, color=OBS_COLORS["O2"]),
            line=dict(width=2.5, dash="dash"),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        template=_TEMPLATE,
        title_text="Overhead Growth by Observability Level",
        title_x=0.5,
        xaxis_title="Observability Level",
        legend=dict(x=0.01, y=0.99),
    )
    fig.update_yaxes(title_text="Mean Latency (ms)", secondary_y=False)
    fig.update_yaxes(title_text="Resource Overhead (KB)", secondary_y=True)
    return fig


# ======================================================================
# 11. Pareto: Usefulness vs Cost
# ======================================================================

def plot_pareto_usefulness_vs_cost(
    df: pd.DataFrame | None = None,
) -> go.Figure:
    """Scatter: resource_overhead vs signal_usefulness, labelled by obs level."""
    df = _ensure_df(df)
    uc = usefulness_vs_cost(df)

    if uc.empty:
        return _empty_figure("Pareto: Usefulness vs Cost")

    uc = uc.sort_values("resource_overhead_kb_mean")

    fig = go.Figure()

    # Individual points
    fig.add_trace(
        go.Scatter(
            x=uc["resource_overhead_kb_mean"],
            y=uc["signal_usefulness_mean"],
            mode="markers+text",
            text=uc["obs_level"],
            textposition="top center",
            marker=dict(
                size=14,
                color=[OBS_COLORS.get(o, "#999") for o in uc["obs_level"]],
                line=dict(width=1.5, color="black"),
            ),
            name="Obs Levels",
        )
    )

    # Pareto front line
    pareto_x: list[float] = []
    pareto_y: list[float] = []
    best_y = -1.0
    for _, row in uc.iterrows():
        if row["signal_usefulness_mean"] > best_y:
            best_y = row["signal_usefulness_mean"]
            pareto_x.append(row["resource_overhead_kb_mean"])
            pareto_y.append(row["signal_usefulness_mean"])

    if len(pareto_x) > 1:
        fig.add_trace(
            go.Scatter(
                x=pareto_x,
                y=pareto_y,
                mode="lines",
                line=dict(dash="dot", color="grey", width=1.5),
                name="Pareto Front",
                showlegend=True,
            )
        )

    fig.update_layout(
        template=_TEMPLATE,
        title_text="Pareto: Signal Usefulness vs Resource Cost",
        title_x=0.5,
        xaxis_title="Resource Overhead (KB)",
        yaxis_title="Signal Usefulness Score",
        legend=dict(x=0.01, y=0.99),
    )
    return fig


# ======================================================================
# 12. Incident Timeline (Case Study)
# ======================================================================

def plot_incident_timeline(df: pd.DataFrame | None = None) -> go.Figure:
    """Timeline for a fault case study: detection time across repeats & obs levels."""
    df = _ensure_df(df)

    # Pick the best candidate fault scenario
    fault_df = df[df["scenario_group"] == "fault"].copy()
    if fault_df.empty:
        return _empty_figure("Incident Timeline")

    # Prefer FLT-003 if present, else first fault scenario with detections
    candidates = fault_df["scenario_id"].unique()
    chosen = "FLT-003" if "FLT-003" in candidates else candidates[0]

    case = fault_df[fault_df["scenario_id"] == chosen].copy()
    case = case.dropna(subset=["time_to_detect_ms"])

    if case.empty:
        # Fallback: show all detections for the chosen scenario
        case = fault_df[fault_df["scenario_id"] == chosen].copy()
        if case.empty:
            return _empty_figure("Incident Timeline")

    fig = go.Figure()
    obs_levels = sorted(case["obs_level"].unique())

    for obs in obs_levels:
        sub = case[case["obs_level"] == obs].sort_values("repeat_idx")
        fig.add_trace(
            go.Scatter(
                x=sub["repeat_idx"],
                y=sub["time_to_detect_ms"],
                mode="lines+markers",
                name=obs,
                marker=dict(size=8, color=OBS_COLORS.get(obs, "#999")),
                line=dict(width=2),
            )
        )

    fig.update_layout(
        template=_TEMPLATE,
        title_text=f"Incident Timeline — {chosen} (Dependency Failure)",
        title_x=0.5,
        xaxis_title="Repeat Index",
        yaxis_title="Time to Detect (ms)",
        legend_title_text="Obs Level",
    )
    return fig


# ---------------------------------------------------------------------------
# Plot 13: Hypothesis test results
# ---------------------------------------------------------------------------

def plot_hypothesis_tests(df=None) -> go.Figure:
    """Bar chart of p-values for all formal hypotheses."""
    try:
        from experiments.analysis.hypothesis_testing import run_hypothesis_tests
    except ImportError:
        return _empty_figure("Hypothesis Tests")

    raw = _ensure_df(df)
    if raw.empty:
        return _empty_figure("Hypothesis Tests")

    report = run_hypothesis_tests(raw)
    hyp_df = report.to_dataframe()
    if hyp_df.empty:
        return _empty_figure("Hypothesis Tests")

    hyp_df = hyp_df.sort_values("p_value")
    colors = ["#00CC96" if sig else "#EF553B" for sig in hyp_df["significant"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=hyp_df["hypothesis"],
        y=hyp_df["p_value"],
        marker_color=colors,
        text=[f"p={v:.4f}" for v in hyp_df["p_value"]],
        textposition="outside",
        name="p-value",
    ))
    fig.add_hline(
        y=0.05,
        line_dash="dash",
        line_color="#FF6692",
        annotation_text="α = 0.05",
        annotation_position="right",
    )
    fig.update_layout(
        template=_TEMPLATE,
        title_text="Statistical Hypothesis Tests (p-values)",
        title_x=0.5,
        xaxis_title="Hypothesis",
        yaxis_title="p-value",
        yaxis=dict(range=[0, max(0.2, float(hyp_df["p_value"].max()) * 1.3)]),
        xaxis_tickangle=-30,
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Plot 14: OES scores and sensitivity
# ---------------------------------------------------------------------------

def plot_oes_scores(df=None) -> go.Figure:
    """Grouped bar chart: OES component breakdown per observability level."""
    try:
        from experiments.analysis.oes import compute_oes_scores, oes_sensitivity
    except ImportError:
        return _empty_figure("OES Scores")

    raw = _ensure_df(df)
    if raw.empty:
        return _empty_figure("OES Scores")

    scores = compute_oes_scores(raw)
    if not scores:
        return _empty_figure("OES Scores")

    levels = [s.obs_level for s in scores]
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("OES Components by Level", "OES Sensitivity (Weight Profiles)"),
    )

    # Left: stacked component breakdown
    components = {
        "Detection": ([s.detection_rate for s in scores], "#636EFA"),
        "Localization": ([s.localization_rate for s in scores], "#EF553B"),
        "Speed": ([s.speed_score for s in scores], "#00CC96"),
        "Cost (penalty)": ([s.cost_score for s in scores], "#FFA15A"),
    }
    for name, (vals, color) in components.items():
        fig.add_trace(go.Bar(
            x=levels, y=vals, name=name,
            marker_color=color,
            legendgroup=name,
        ), row=1, col=1)

    # OES total line on left axis
    fig.add_trace(go.Scatter(
        x=levels,
        y=[s.oes for s in scores],
        mode="lines+markers+text",
        name="OES total",
        marker=dict(size=10, color="#AB63FA"),
        line=dict(width=3, color="#AB63FA", dash="dot"),
        text=[f"{s.oes:.3f}" for s in scores],
        textposition="top center",
        legendgroup="OES",
    ), row=1, col=1)

    # Right: sensitivity across weight profiles
    sens_df = oes_sensitivity(raw)
    if not sens_df.empty:
        for profile in sens_df["weight_profile"].unique():
            sub = sens_df[sens_df["weight_profile"] == profile]
            fig.add_trace(go.Scatter(
                x=sub["obs_level"],
                y=sub["oes"],
                mode="lines+markers",
                name=profile,
                legendgroup=profile,
            ), row=1, col=2)

    fig.update_layout(
        template=_TEMPLATE,
        title_text="Observability Effectiveness Score (OES)",
        title_x=0.5,
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=-0.35),
    )
    return fig


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _empty_figure(title: str) -> go.Figure:
    """Return an empty figure with a 'no data' annotation."""
    fig = go.Figure()
    fig.update_layout(
        template=_TEMPLATE,
        title_text=title,
        title_x=0.5,
        annotations=[
            dict(
                text="No data available",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=20, color="grey"),
            )
        ],
    )
    return fig
