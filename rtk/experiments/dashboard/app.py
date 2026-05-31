"""Dash dashboard — Interactive research presentation layer.

Thin layer on top of pre-computed aggregated data.
Not the place where research logic lives — only presentation.
"""
from __future__ import annotations

from pathlib import Path

import dash
from dash import html, dcc, callback, Input, Output
import pandas as pd

from experiments.analysis.statistics import load_raw_runs
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

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
_DATA_PATH = Path(__file__).resolve().parents[1] / "results" / "raw_runs.jsonl"


def _load_data() -> pd.DataFrame | None:
    """Return DataFrame or *None* when data file is missing."""
    if not _DATA_PATH.exists():
        return None
    return load_raw_runs(_DATA_PATH.parent)


# ---------------------------------------------------------------------------
# Dash application
# ---------------------------------------------------------------------------
app = dash.Dash(__name__, title="Дипломное исследование")

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
_SIDEBAR: dict = {
    "width": "260px",
    "position": "fixed",
    "top": 0,
    "left": 0,
    "bottom": 0,
    "padding": "1.5rem 1rem",
    "backgroundColor": "#f8f9fa",
    "overflowY": "auto",
}

_CONTENT: dict = {
    "marginLeft": "280px",
    "padding": "1.5rem 2rem",
}

_DROPDOWN: dict = {
    "width": "220px",
    "display": "inline-block",
    "marginRight": "1rem",
    "verticalAlign": "top",
}

_DESCRIPTION: dict = {
    "color": "#555",
    "fontSize": "0.9rem",
    "marginBottom": "1rem",
}

# ---------------------------------------------------------------------------
# Tab definitions
# ---------------------------------------------------------------------------
TAB_DEFS = [
    ("verification", "Верификация"),
    ("comparative", "Сравнительный анализ"),
    ("fault", "Fault Observability"),
    ("exvivo", "Ex-Vivo регрессия"),
    ("overhead", "Overhead / Decision"),
    ("casestudy", "Case Study"),
]

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = html.Div([
    # Sidebar
    html.Div([
        html.H3("Дипломное исследование — Панель результатов",
                 style={"fontSize": "1.1rem", "marginBottom": "1.5rem"}),
        dcc.Tabs(
            id="nav-tabs",
            value="verification",
            vertical=True,
            children=[
                dcc.Tab(label=label, value=value)
                for value, label in TAB_DEFS
            ],
            style={"width": "100%"},
        ),
    ], style=_SIDEBAR),

    # Main content
    html.Div(id="page-content", style=_CONTENT),
])


# ---------------------------------------------------------------------------
# Helper: error placeholder when data is missing
# ---------------------------------------------------------------------------
def _no_data_message() -> html.Div:
    return html.Div([
        html.H4("⚠ Данные не найдены"),
        html.P(
            f"Файл {_DATA_PATH} не обнаружен. "
            "Запустите эксперименты (experiments/run_experiments.py), "
            "чтобы сгенерировать raw_runs.jsonl.",
            style=_DESCRIPTION,
        ),
    ])


# ---------------------------------------------------------------------------
# Panel builders
# ---------------------------------------------------------------------------

def _verification_panel(df: pd.DataFrame) -> html.Div:
    return html.Div([
        html.H4("Верификация"),
        html.P(
            "Сводка по верификационным прогонам и состав тестового стека.",
            style=_DESCRIPTION,
        ),
        dcc.Graph(figure=plot_verification_summary(df)),
        dcc.Graph(figure=plot_test_stack_composition(df)),
    ])


def _comparative_panel(df: pd.DataFrame) -> html.Div:
    modes = sorted(df["mode"].dropna().unique()) if "mode" in df.columns else []
    obs_levels = sorted(df["obs_level"].dropna().unique()) if "obs_level" in df.columns else []

    return html.Div([
        html.H4("Сравнительный анализ"),
        html.P(
            "Матрица сценариев и сравнительный вид метрик по режимам.",
            style=_DESCRIPTION,
        ),
        html.Div([
            html.Div([
                html.Label("Режим (mode)"),
                dcc.Dropdown(
                    id="comp-mode",
                    options=[{"label": m, "value": m} for m in modes],
                    value=None,
                    placeholder="Все",
                    clearable=True,
                ),
            ], style=_DROPDOWN),
            html.Div([
                html.Label("Уровень наблюдаемости"),
                dcc.Dropdown(
                    id="comp-obs",
                    options=[{"label": o, "value": o} for o in obs_levels],
                    value=None,
                    placeholder="Все",
                    clearable=True,
                ),
            ], style=_DROPDOWN),
        ], style={"marginBottom": "1rem"}),
        dcc.Graph(id="comp-matrix"),
        dcc.Graph(id="comp-view"),
    ])


def _fault_panel(df: pd.DataFrame) -> html.Div:
    return html.Div([
        html.H4("Fault Observability"),
        html.P(
            "Тепловая карта обнаружения сбоев и распределение времени до обнаружения.",
            style=_DESCRIPTION,
        ),
        dcc.Graph(figure=plot_fault_observability_heatmap(df)),
        dcc.Graph(figure=plot_time_to_detect_distribution(df)),
    ])


def _exvivo_panel(df: pd.DataFrame) -> html.Div:
    return html.Div([
        html.H4("Ex-Vivo регрессия"),
        html.P(
            "Воронка прогона ex-vivo и сравнение с базовой линией.",
            style=_DESCRIPTION,
        ),
        dcc.Graph(figure=plot_exvivo_funnel(df)),
        dcc.Graph(figure=plot_exvivo_vs_baseline(df)),
    ])


def _overhead_panel(df: pd.DataFrame) -> html.Div:
    obs_levels = sorted(df["obs_level"].dropna().unique()) if "obs_level" in df.columns else []

    return html.Div([
        html.H4("Overhead / Decision"),
        html.P(
            "Анализ накладных расходов, Парето-граница полезность-стоимость, "
            "вклад сигналов.",
            style=_DESCRIPTION,
        ),
        html.Div([
            html.Div([
                html.Label("Уровень наблюдаемости"),
                dcc.Dropdown(
                    id="ovh-obs",
                    options=[{"label": o, "value": o} for o in obs_levels],
                    value=None,
                    placeholder="Все",
                    clearable=True,
                ),
            ], style=_DROPDOWN),
        ], style={"marginBottom": "1rem"}),
        dcc.Graph(id="ovh-level"),
        dcc.Graph(id="ovh-pareto"),
        dcc.Graph(id="ovh-signal"),
    ])


def _casestudy_panel(df: pd.DataFrame) -> html.Div:
    groups = sorted(df["scenario_group"].dropna().unique()) if "scenario_group" in df.columns else []

    return html.Div([
        html.H4("Case Study"),
        html.P(
            "Временная шкала инцидентов для выбранной группы сценариев.",
            style=_DESCRIPTION,
        ),
        html.Div([
            html.Div([
                html.Label("Группа сценариев"),
                dcc.Dropdown(
                    id="cs-group",
                    options=[{"label": g, "value": g} for g in groups],
                    value=None,
                    placeholder="Все",
                    clearable=True,
                ),
            ], style=_DROPDOWN),
        ], style={"marginBottom": "1rem"}),
        dcc.Graph(id="cs-timeline"),
    ])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(Output("page-content", "children"), Input("nav-tabs", "value"))
def render_tab(tab: str):
    df = _load_data()
    if df is None:
        return _no_data_message()

    builders = {
        "verification": _verification_panel,
        "comparative": _comparative_panel,
        "fault": _fault_panel,
        "exvivo": _exvivo_panel,
        "overhead": _overhead_panel,
        "casestudy": _casestudy_panel,
    }
    builder = builders.get(tab)
    if builder is None:
        return html.P("Неизвестная вкладка.")
    return builder(df)


@callback(
    Output("comp-matrix", "figure"),
    Output("comp-view", "figure"),
    Input("comp-mode", "value"),
    Input("comp-obs", "value"),
)
def update_comparative(mode: str | None, obs: str | None):
    df = _load_data()
    if df is None:
        return dash.no_update, dash.no_update
    if mode:
        df = df[df["mode"] == mode]
    if obs:
        df = df[df["obs_level"] == obs]
    return plot_scenario_matrix(df), plot_comparative_view(df)


@callback(
    Output("ovh-level", "figure"),
    Output("ovh-pareto", "figure"),
    Output("ovh-signal", "figure"),
    Input("ovh-obs", "value"),
)
def update_overhead(obs: str | None):
    df = _load_data()
    if df is None:
        return dash.no_update, dash.no_update, dash.no_update
    if obs:
        df = df[df["obs_level"] == obs]
    return (
        plot_overhead_by_obs_level(df),
        plot_pareto_usefulness_vs_cost(df),
        plot_signal_contribution(df),
    )


@callback(Output("cs-timeline", "figure"), Input("cs-group", "value"))
def update_casestudy(group: str | None):
    df = _load_data()
    if df is None:
        return dash.no_update
    if group:
        df = df[df["scenario_group"] == group]
    return plot_incident_timeline(df)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_dashboard(host: str = "127.0.0.1", port: int = 8050, debug: bool = False):
    """Start the Dash development server."""
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard(debug=True)
