"""Scientific document support — artifact generation for diploma text.

Produces tables (CSV), static plots (PNG/SVG), summary files (JSON/Markdown),
experiment parameters, and reproducibility metadata.

Usage::

    python -m experiments.sciexport --results experiments/results
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from experiments.data_contracts.schemas import RawRunRecord, ALL_SCENARIOS
from experiments.dataset.writer import DatasetWriter


# ------------------------------------------------------------------
# Reproducibility metadata
# ------------------------------------------------------------------

def gather_reproducibility_metadata(
    results_dir: str = "experiments/results",
    n_repeats: int = 3,
) -> Dict[str, Any]:
    """Collect reproducibility metadata for the experiment run."""
    git_sha = "unknown"
    try:
        git_sha = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        pass

    return {
        "commit": git_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario_set": [s.scenario_id for s in ALL_SCENARIOS],
        "total_scenarios": len(ALL_SCENARIOS),
        "repeats": n_repeats,
        "obs_levels": ["O0", "O1", "O2"],
        "modes": ["A0", "A1", "A2", "A3"],
        "results_dir": os.path.abspath(results_dir),
    }


# ------------------------------------------------------------------
# Table export
# ------------------------------------------------------------------

def export_diploma_tables(
    records: List[RawRunRecord],
    output_dir: str = "results/tables",
) -> List[str]:
    """Generate CSV tables from raw run records for the diploma chapter.

    Returns a list of file paths written.
    """
    try:
        import pandas as pd
    except ImportError:
        return []

    output_dir_p = Path(output_dir)
    output_dir_p.mkdir(parents=True, exist_ok=True)
    written: List[str] = []

    rows = [r.__dict__ for r in records]
    if not rows:
        return written

    df = pd.DataFrame(rows)

    # Table 1: Detection rate by mode
    if "mode" in df.columns and "actual_detection" in df.columns:
        tbl = df.groupby("mode").agg(
            total_runs=("actual_detection", "count"),
            detected=("actual_detection", "sum"),
        ).reset_index()
        tbl["detection_rate"] = (tbl["detected"] / tbl["total_runs"]).round(4)
        path = str(output_dir_p / "detection_by_mode.csv")
        tbl.to_csv(path, index=False)
        written.append(path)

    # Table 2: Detection rate by mode × obs_level
    if "obs_level" in df.columns:
        tbl = df.groupby(["mode", "obs_level"]).agg(
            total_runs=("actual_detection", "count"),
            detected=("actual_detection", "sum"),
        ).reset_index()
        tbl["detection_rate"] = (tbl["detected"] / tbl["total_runs"]).round(4)
        path = str(output_dir_p / "detection_by_mode_obs.csv")
        tbl.to_csv(path, index=False)
        written.append(path)

    # Table 3: Overhead by observability level
    oh_cols = {"latency_mean_ms", "throughput_rps", "resource_overhead_kb", "variance_growth"}
    if oh_cols.issubset(df.columns):
        tbl = df.groupby("obs_level").agg(
            mean_latency=("latency_mean_ms", "mean"),
            mean_throughput=("throughput_rps", "mean"),
            mean_overhead_kb=("resource_overhead_kb", "mean"),
            mean_variance=("variance_growth", "mean"),
        ).round(3).reset_index()
        path = str(output_dir_p / "overhead_by_obs.csv")
        tbl.to_csv(path, index=False)
        written.append(path)

    # Table 4: Scenario detection matrix
    if "scenario_id" in df.columns:
        tbl = df.groupby(["scenario_id", "mode"]).agg(
            detection_rate=("actual_detection", "mean"),
        ).reset_index()
        pivot = tbl.pivot(index="scenario_id", columns="mode", values="detection_rate")
        pivot = pivot.round(4).fillna(0)
        path = str(output_dir_p / "scenario_matrix.csv")
        pivot.to_csv(path)
        written.append(path)

    # Table 5: Fault observability heatmap data
    fault_df = df[df["scenario_group"] == "fault"]
    if len(fault_df) > 0:
        tbl = fault_df.groupby(["scenario_id", "obs_level"]).agg(
            detection_rate=("actual_detection", "mean"),
        ).reset_index()
        pivot = tbl.pivot(index="scenario_id", columns="obs_level", values="detection_rate")
        pivot = pivot.round(4).fillna(0)
        path = str(output_dir_p / "fault_heatmap.csv")
        pivot.to_csv(path)
        written.append(path)

    # Table 6: Ex-vivo match rates
    exvivo_df = df[df["mode"].isin(["A1", "A3"])]
    if len(exvivo_df) > 0:
        tbl = exvivo_df.groupby(["mode", "scenario_id"]).agg(
            mean_match_rate=("exvivo_match_rate", "mean"),
            total_regressions=("regressions_found", "sum"),
        ).round(4).reset_index()
        path = str(output_dir_p / "exvivo_match_rates.csv")
        tbl.to_csv(path, index=False)
        written.append(path)

    # Table 7: Hypothesis testing results
    try:
        from experiments.analysis.hypothesis_testing import run_hypothesis_tests
        report = run_hypothesis_tests(df)
        hyp_df = report.to_dataframe()
        if not hyp_df.empty:
            path = str(output_dir_p / "hypothesis_tests.csv")
            hyp_df.to_csv(path, index=False)
            written.append(path)
    except Exception:
        pass

    # Table 8: OES scores
    try:
        from experiments.analysis.oes import oes_dataframe, oes_pareto_frontier, oes_sensitivity
        oes_df = oes_dataframe(df)
        if not oes_df.empty:
            pareto_df = oes_pareto_frontier(oes_df)
            path = str(output_dir_p / "oes_scores.csv")
            pareto_df.to_csv(path, index=False)
            written.append(path)

            sens_df = oes_sensitivity(df)
            if not sens_df.empty:
                path = str(output_dir_p / "oes_sensitivity.csv")
                sens_df.to_csv(path, index=False)
                written.append(path)
    except Exception:
        pass

    return written


# ------------------------------------------------------------------
# Summary export
# ------------------------------------------------------------------

def export_summary_json(
    records: List[RawRunRecord],
    output_dir: str = "results/summary",
    n_repeats: int = 3,
) -> str:
    """Write a summary JSON file for the diploma chapter."""
    output_dir_p = Path(output_dir)
    output_dir_p.mkdir(parents=True, exist_ok=True)

    total = len(records)
    detected = sum(1 for r in records if r.actual_detection)
    localized = sum(1 for r in records if r.actual_localization)
    modes = sorted(set(r.mode for r in records))
    obs_levels = sorted(set(r.obs_level for r in records))
    scenarios = sorted(set(r.scenario_id for r in records))

    summary: Dict[str, Any] = {
        "total_runs": total,
        "detected": detected,
        "localized": localized,
        "detection_rate": round(detected / total, 4) if total else 0,
        "localization_rate": round(localized / total, 4) if total else 0,
        "modes": modes,
        "obs_levels": obs_levels,
        "scenarios": scenarios,
        "reproducibility": gather_reproducibility_metadata(
            n_repeats=n_repeats,
        ),
    }

    path = output_dir_p / "experiment_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def export_summary_markdown(
    records: List[RawRunRecord],
    output_dir: str = "results/summary",
) -> str:
    """Write a Markdown summary suitable for inclusion in the diploma text."""
    output_dir_p = Path(output_dir)
    output_dir_p.mkdir(parents=True, exist_ok=True)

    total = len(records)
    detected = sum(1 for r in records if r.actual_detection)
    localized = sum(1 for r in records if r.actual_localization)

    by_mode: Dict[str, List[RawRunRecord]] = {}
    for r in records:
        by_mode.setdefault(r.mode, []).append(r)

    lines = [
        "# Результаты эксперимента\n",
        f"**Всего прогонов:** {total}  ",
        f"**Обнаружено:** {detected} ({detected / total * 100:.1f}%)  " if total else "",
        f"**Локализовано:** {localized} ({localized / total * 100:.1f}%)  \n" if total else "",
        "## Результаты по режимам\n",
        "| Режим | Прогоны | Detection rate | Localization rate | Avg latency (ms) |",
        "|-------|---------|---------------|------------------|-------------------|",
    ]

    for mode in sorted(by_mode):
        grp = by_mode[mode]
        n = len(grp)
        det = sum(1 for r in grp if r.actual_detection)
        loc = sum(1 for r in grp if r.actual_localization)
        lat = sum(r.latency_mean_ms for r in grp) / n if n else 0
        lines.append(
            f"| {mode} | {n} | {det / n:.2%} | {loc / n:.2%} | {lat:.2f} |"
        )

    lines.append("")

    # A2 breakdown by obs level
    a2 = by_mode.get("A2", [])
    if a2:
        lines.append("## A2: по уровням наблюдаемости\n")
        lines.append("| Obs level | Прогоны | Detection rate |")
        lines.append("|-----------|---------|---------------|")
        by_obs: Dict[str, List[RawRunRecord]] = {}
        for r in a2:
            by_obs.setdefault(r.obs_level, []).append(r)
        for lvl in sorted(by_obs):
            grp = by_obs[lvl]
            n = len(grp)
            det = sum(1 for r in grp if r.actual_detection)
            lines.append(f"| {lvl} | {n} | {det / n:.2%} |")
        lines.append("")

    path = output_dir_p / "experiment_summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------
# Figure export (delegates to visualization layer)
# ------------------------------------------------------------------

def export_diploma_figures(
    results_dir: str = "experiments/results",
    output_dir: str = "results/figures",
    formats: tuple = ("png", "svg"),
) -> List[str]:
    """Generate static figures for the diploma from raw dataset.

    Returns list of file paths written.
    """
    try:
        from experiments.visualization.export import export_all_plots
    except ImportError:
        return []

    raw_path = os.path.join(results_dir, "raw_runs.jsonl")
    if not os.path.exists(raw_path):
        return []

    try:
        import pandas as pd
        df = pd.read_json(raw_path, lines=True)
    except (ValueError, FileNotFoundError) as exc:
        return []

    return export_all_plots(df=df, output_dir=output_dir, formats=formats)
