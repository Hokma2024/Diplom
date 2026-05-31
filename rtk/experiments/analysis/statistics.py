"""Analysis module — Aggregation and statistical analysis.

Loads raw_runs.jsonl, computes aggregates, confidence intervals,
and prepares data for visualization and diploma tables.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RESULTS_DIR = Path("experiments/results")

# z-value for 95 % confidence interval
_Z95 = 1.96


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_raw_runs(results_dir: Path | str | None = None) -> pd.DataFrame:
    """Load *raw_runs.jsonl* into a :class:`~pandas.DataFrame`."""
    d = Path(results_dir) if results_dir else RESULTS_DIR
    path = d / "raw_runs.jsonl"
    records: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_groupby(
    df: pd.DataFrame,
    by: list[str],
    required_cols: list[str] | None = None,
) -> pd.core.groupby.DataFrameGroupBy | None:
    """Return a GroupBy object or *None* when the DataFrame is unusable."""
    if df.empty:
        return None
    needed = set(by) | set(required_cols or [])
    if not needed.issubset(df.columns):
        return None
    return df.groupby(by)


def _proportion_ci(p: float, n: int) -> tuple[float, float]:
    """Normal-approximation 95 % CI for a proportion."""
    if n == 0:
        return (0.0, 0.0)
    se = math.sqrt(p * (1 - p) / n)
    lo = max(0.0, p - _Z95 * se)
    hi = min(1.0, p + _Z95 * se)
    return (lo, hi)


def _empty_df(columns: list[str]) -> pd.DataFrame:
    """Return an empty DataFrame with the requested columns."""
    return pd.DataFrame(columns=columns)


# ---------------------------------------------------------------------------
# Detection & localisation rates
# ---------------------------------------------------------------------------

def detection_rate_by_mode(df: pd.DataFrame) -> pd.DataFrame:
    """Detection rate grouped by *mode*.

    Returns columns: mode, detection_rate, n, ci_lower, ci_upper.
    """
    cols = ["mode", "detection_rate", "n", "ci_lower", "ci_upper"]
    needed = {"mode", "actual_detection"}
    if df.empty or not needed.issubset(df.columns):
        return _empty_df(cols)

    rows: list[dict[str, Any]] = []
    for mode, sub in df.groupby("mode"):
        vals = sub["actual_detection"].dropna()
        n = len(vals)
        rate = float(vals.mean()) if n else 0.0
        lo, hi = _proportion_ci(rate, n)
        rows.append({
            "mode": mode,
            "detection_rate": rate,
            "n": n,
            "ci_lower": lo,
            "ci_upper": hi,
        })
    return pd.DataFrame(rows, columns=cols)


def detection_rate_by_mode_obs(df: pd.DataFrame) -> pd.DataFrame:
    """Detection rate by *mode* and *obs_level*.

    Returns columns: mode, obs_level, detection_rate, n, ci_lower, ci_upper.
    """
    cols = ["mode", "obs_level", "detection_rate", "n", "ci_lower", "ci_upper"]
    grp = _safe_groupby(df, ["mode", "obs_level"], ["actual_detection"])
    if grp is None:
        return _empty_df(cols)

    rows: list[dict[str, Any]] = []
    for (mode, obs), sub in grp:
        vals = sub["actual_detection"].dropna()
        n = len(vals)
        rate = float(vals.mean()) if n else 0.0
        lo, hi = _proportion_ci(rate, n)
        rows.append({
            "mode": mode,
            "obs_level": obs,
            "detection_rate": rate,
            "n": n,
            "ci_lower": lo,
            "ci_upper": hi,
        })
    return pd.DataFrame(rows, columns=cols)


def localization_rate_by_mode_obs(df: pd.DataFrame) -> pd.DataFrame:
    """Localization rate by *mode* and *obs_level*.

    Returns columns: mode, obs_level, localization_rate, n, ci_lower, ci_upper.
    """
    cols = [
        "mode", "obs_level", "localization_rate",
        "n", "ci_lower", "ci_upper",
    ]
    grp = _safe_groupby(df, ["mode", "obs_level"], ["actual_localization"])
    if grp is None:
        return _empty_df(cols)

    rows: list[dict[str, Any]] = []
    for (mode, obs), sub in grp:
        vals = sub["actual_localization"].dropna()
        n = len(vals)
        rate = float(vals.mean()) if n else 0.0
        lo, hi = _proportion_ci(rate, n)
        rows.append({
            "mode": mode,
            "obs_level": obs,
            "localization_rate": rate,
            "n": n,
            "ci_lower": lo,
            "ci_upper": hi,
        })
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# Time-to-detect / time-to-localize distributions
# ---------------------------------------------------------------------------

def _time_distribution(
    df: pd.DataFrame,
    filter_col: str,
    time_col: str,
    label: str,
) -> pd.DataFrame:
    """Generic helper for time-distribution statistics."""
    stat_cols = [
        "mode", "obs_level",
        f"{label}_mean", f"{label}_median", f"{label}_std",
        f"{label}_p95", f"{label}_p99", "n",
    ]
    needed = {filter_col, time_col, "mode", "obs_level"}
    if df.empty or not needed.issubset(df.columns):
        return _empty_df(stat_cols)

    subset = df[df[filter_col].astype(bool)].copy()
    if subset.empty:
        return _empty_df(stat_cols)

    rows: list[dict[str, Any]] = []
    for (mode, obs), sub in subset.groupby(["mode", "obs_level"]):
        vals = sub[time_col].dropna()
        n = len(vals)
        if n == 0:
            continue
        rows.append({
            "mode": mode,
            "obs_level": obs,
            f"{label}_mean": float(vals.mean()),
            f"{label}_median": float(vals.median()),
            f"{label}_std": float(vals.std()) if n > 1 else 0.0,
            f"{label}_p95": float(np.percentile(vals, 95)),
            f"{label}_p99": float(np.percentile(vals, 99)),
            "n": n,
        })
    return pd.DataFrame(rows, columns=stat_cols)


def time_to_detect_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Time-to-detect statistics by *mode* and *obs_level*.

    Only rows where ``actual_detection`` is true are considered.
    """
    return _time_distribution(df, "actual_detection", "time_to_detect_ms", "ttd")


def time_to_localize_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Time-to-localize statistics by *mode* and *obs_level*.

    Only rows where ``actual_localization`` is true are considered.
    """
    return _time_distribution(
        df, "actual_localization", "time_to_localize_ms", "ttl",
    )


# ---------------------------------------------------------------------------
# Ex-vivo match rates
# ---------------------------------------------------------------------------

def exvivo_match_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Ex-vivo match rate by *mode* and *scenario_group*.

    Considers only modes that participate in ex-vivo testing (A1, A3).
    """
    cols = ["mode", "scenario_group", "exvivo_match_rate_mean", "n"]
    needed = {"mode", "scenario_group", "exvivo_match_rate"}
    if df.empty or not needed.issubset(df.columns):
        return _empty_df(cols)

    subset = df[df["mode"].isin(["A1", "A3"])].copy()
    if subset.empty:
        return _empty_df(cols)

    rows: list[dict[str, Any]] = []
    for (mode, sg), sub in subset.groupby(["mode", "scenario_group"]):
        vals = sub["exvivo_match_rate"].dropna()
        n = len(vals)
        rows.append({
            "mode": mode,
            "scenario_group": sg,
            "exvivo_match_rate_mean": float(vals.mean()) if n else 0.0,
            "n": n,
        })
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# Regressions
# ---------------------------------------------------------------------------

def regressions_by_type(df: pd.DataFrame) -> pd.DataFrame:
    """Regressions found by *scenario_id* and *mode*.

    Filters to regression scenarios only (``scenario_group == 'regression'``).
    """
    cols = ["scenario_id", "mode", "total_regressions", "n"]
    needed = {"scenario_group", "scenario_id", "mode", "regressions_found"}
    if df.empty or not needed.issubset(df.columns):
        return _empty_df(cols)

    subset = df[df["scenario_group"] == "regression"].copy()
    if subset.empty:
        return _empty_df(cols)

    rows: list[dict[str, Any]] = []
    for (sid, mode), sub in subset.groupby(["scenario_id", "mode"]):
        vals = sub["regressions_found"].dropna()
        rows.append({
            "scenario_id": sid,
            "mode": mode,
            "total_regressions": int(vals.sum()),
            "n": len(vals),
        })
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# Fault observability heatmap
# ---------------------------------------------------------------------------

def fault_observability_heatmap_data(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot table: *scenario_id* × *obs_level* → detection rate.

    Filters to fault scenarios (``scenario_group == 'fault'``).
    """
    needed = {"scenario_group", "scenario_id", "obs_level", "actual_detection"}
    if df.empty or not needed.issubset(df.columns):
        return pd.DataFrame()

    subset = df[df["scenario_group"] == "fault"].copy()
    if subset.empty:
        return pd.DataFrame()

    pivot = subset.pivot_table(
        index="scenario_id",
        columns="obs_level",
        values="actual_detection",
        aggfunc="mean",
    )
    pivot.columns.name = None
    return pivot


# ---------------------------------------------------------------------------
# Overhead metrics
# ---------------------------------------------------------------------------

def overhead_by_obs_level(df: pd.DataFrame) -> pd.DataFrame:
    """Mean overhead metrics grouped by *obs_level*.

    Returns: obs_level, latency_mean_ms, throughput_rps,
             resource_overhead_kb, variance_growth, n.
    """
    metric_cols = [
        "latency_mean_ms", "throughput_rps",
        "resource_overhead_kb", "variance_growth",
    ]
    out_cols = ["obs_level"] + metric_cols + ["n"]
    if df.empty or "obs_level" not in df.columns:
        return _empty_df(out_cols)

    available = [c for c in metric_cols if c in df.columns]
    if not available:
        return _empty_df(out_cols)

    rows: list[dict[str, Any]] = []
    for obs, sub in df.groupby("obs_level"):
        row: dict[str, Any] = {"obs_level": obs, "n": len(sub)}
        for col in metric_cols:
            if col in sub.columns:
                row[col] = float(sub[col].dropna().mean()) if not sub[col].dropna().empty else 0.0
            else:
                row[col] = 0.0
        rows.append(row)
    return pd.DataFrame(rows, columns=out_cols)


# ---------------------------------------------------------------------------
# Signal contribution
# ---------------------------------------------------------------------------

def signal_contribution(df: pd.DataFrame) -> pd.DataFrame:
    """Frequency of each signal type across all runs.

    Parses the ``signal_types_used`` column (comma-separated).
    Returns columns: signal_type, count.
    """
    cols = ["signal_type", "count"]
    if df.empty or "signal_types_used" not in df.columns:
        return _empty_df(cols)

    counter: dict[str, int] = {}
    for raw in df["signal_types_used"].dropna():
        for token in str(raw).split(","):
            token = token.strip()
            if token:
                counter[token] = counter.get(token, 0) + 1

    if not counter:
        return _empty_df(cols)

    result = (
        pd.DataFrame(list(counter.items()), columns=cols)
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )
    return result


# ---------------------------------------------------------------------------
# Usefulness vs cost
# ---------------------------------------------------------------------------

def usefulness_vs_cost(df: pd.DataFrame) -> pd.DataFrame:
    """Signal usefulness vs resource overhead by *obs_level*.

    Returns: obs_level, signal_usefulness_mean, resource_overhead_kb_mean, n.
    """
    cols = ["obs_level", "signal_usefulness_mean", "resource_overhead_kb_mean", "n"]
    needed = {"obs_level", "signal_usefulness_score", "resource_overhead_kb"}
    if df.empty or not needed.issubset(df.columns):
        return _empty_df(cols)

    rows: list[dict[str, Any]] = []
    for obs, sub in df.groupby("obs_level"):
        su = sub["signal_usefulness_score"].dropna()
        ro = sub["resource_overhead_kb"].dropna()
        rows.append({
            "obs_level": obs,
            "signal_usefulness_mean": float(su.mean()) if len(su) else 0.0,
            "resource_overhead_kb_mean": float(ro.mean()) if len(ro) else 0.0,
            "n": len(sub),
        })
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# Scenario matrix
# ---------------------------------------------------------------------------

def scenario_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Scenario detection matrix: *scenario_id* × *mode* → detection rate."""
    needed = {"scenario_id", "mode", "actual_detection"}
    if df.empty or not needed.issubset(df.columns):
        return pd.DataFrame()

    pivot = df.pivot_table(
        index="scenario_id",
        columns="mode",
        values="actual_detection",
        aggfunc="mean",
    )
    pivot.columns.name = None
    return pivot


# ---------------------------------------------------------------------------
# Verification summary
# ---------------------------------------------------------------------------

def verification_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Compute high-level verification summary statistics."""
    if df.empty:
        return {
            "total_runs": 0,
            "modes": [],
            "scenarios": [],
            "obs_levels": [],
            "detection_pass": 0,
            "detection_fail": 0,
            "localization_pass": 0,
            "localization_fail": 0,
        }

    det = df["actual_detection"] if "actual_detection" in df.columns else pd.Series(dtype=bool)
    loc = df["actual_localization"] if "actual_localization" in df.columns else pd.Series(dtype=bool)

    return {
        "total_runs": len(df),
        "modes": sorted(df["mode"].dropna().unique().tolist()) if "mode" in df.columns else [],
        "scenarios": sorted(df["scenario_id"].dropna().unique().tolist()) if "scenario_id" in df.columns else [],
        "obs_levels": sorted(df["obs_level"].dropna().unique().tolist()) if "obs_level" in df.columns else [],
        "detection_pass": int(det.sum()) if len(det) else 0,
        "detection_fail": int((~det.astype(bool)).sum()) if len(det) else 0,
        "localization_pass": int(loc.sum()) if len(loc) else 0,
        "localization_fail": int((~loc.astype(bool)).sum()) if len(loc) else 0,
    }


# ---------------------------------------------------------------------------
# Test stack composition
# ---------------------------------------------------------------------------

def test_stack_composition(df: pd.DataFrame) -> pd.DataFrame:
    """Count of runs by *scenario_group*.

    Returns columns: scenario_group, count.
    """
    cols = ["scenario_group", "count"]
    if df.empty or "scenario_group" not in df.columns:
        return _empty_df(cols)

    result = (
        df.groupby("scenario_group")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )
    return result


# ---------------------------------------------------------------------------
# Diploma table generation
# ---------------------------------------------------------------------------

def generate_diploma_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Generate all tables needed for the diploma text.

    Returns a dictionary mapping table name → DataFrame.
    """
    return {
        "detection_by_mode": detection_rate_by_mode(df),
        "detection_by_mode_obs": detection_rate_by_mode_obs(df),
        "localization_by_mode_obs": localization_rate_by_mode_obs(df),
        "ttd_distribution": time_to_detect_distribution(df),
        "ttl_distribution": time_to_localize_distribution(df),
        "exvivo_match": exvivo_match_rates(df),
        "regressions": regressions_by_type(df),
        "fault_heatmap": fault_observability_heatmap_data(df),
        "overhead": overhead_by_obs_level(df),
        "signal_contribution": signal_contribution(df),
        "usefulness_vs_cost": usefulness_vs_cost(df),
        "scenario_matrix": scenario_matrix(df),
        "test_composition": test_stack_composition(df),
    }
