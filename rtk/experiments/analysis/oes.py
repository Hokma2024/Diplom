"""Observability Effectiveness Score (OES) — composite metric.

OES quantifies the overall value of an observability configuration by
weighting detection capability, localization precision, response speed,
and resource cost into a single comparable score.

Formula
-------
OES = w_det  × detection_rate
    + w_loc  × localization_rate
    + w_spd  × speed_score          # normalized 1/TTD
    - w_cst  × cost_score           # normalized overhead

Default weights (sum to 1.0 before the cost subtraction):
    w_det  = 0.45   detection is the primary value signal
    w_loc  = 0.30   localization reduces MTTR
    w_spd  = 0.15   faster detection matters but less than coverage
    w_cst  = 0.10   cost is a penalty, not a disqualifier

Score range: [0, 1] — higher is better.

Pareto efficiency
-----------------
oes_pareto_frontier(df) returns the subset of (obs_level, OES, cost)
points that are not dominated: for each point, there is no other point
that is simultaneously higher in OES and lower in cost.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Default weight profile
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: Dict[str, float] = {
    "detection":     0.45,
    "localization":  0.30,
    "speed":         0.15,
    "cost":          0.10,
}


# ---------------------------------------------------------------------------
# OES result containers
# ---------------------------------------------------------------------------

@dataclass
class OESScore:
    """OES decomposition for one observability level."""
    obs_level: str
    detection_rate: float
    localization_rate: float
    speed_score: float          # normalised, higher = faster detection
    cost_score: float           # normalised, higher = more expensive
    oes: float                  # composite score
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    n: int = 0

    def as_dict(self) -> Dict[str, float]:
        return {
            "obs_level":        self.obs_level,
            "detection_rate":   round(self.detection_rate, 4),
            "localization_rate": round(self.localization_rate, 4),
            "speed_score":      round(self.speed_score, 4),
            "cost_score":       round(self.cost_score, 4),
            "oes":              round(self.oes, 4),
            "n":                self.n,
        }


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _safe_norm(values: List[float]) -> List[float]:
    """Min-max normalise; returns list of same length in [0, 1]."""
    arr = np.array(values, dtype=float)
    lo, hi = arr.min(), arr.max()
    if hi == lo:
        return [0.5] * len(values)
    return list((arr - lo) / (hi - lo))


def _speed_from_ttd(ttd_values: List[Optional[float]]) -> float:
    """Convert a list of TTD observations to a speed score in [0, 1].

    Observations where detection did not occur contribute 0 (no speed).
    Lower TTD = higher speed.  The score is based on the inverse median.
    Returns 0 if no detections.
    """
    valid = [v for v in ttd_values if v is not None and not math.isnan(v) and v >= 0]
    if not valid:
        return 0.0
    median_ttd = float(np.median(valid))
    # Use inverse with a cap of 1000 ms as reference slow detection
    ref_slow_ms = 1000.0
    return min(1.0, ref_slow_ms / (median_ttd + 1e-6))


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_oes_scores(
    df: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None,
) -> List[OESScore]:
    """Compute OES for each observability level across A2 fault scenarios.

    Parameters
    ----------
    df:
        Raw runs DataFrame.  Must contain: mode, obs_level, scenario_group,
        actual_detection, actual_localization, time_to_detect_ms,
        resource_overhead_kb, variance_growth.
    weights:
        Custom weight dict (keys: detection, localization, speed, cost).
        Falls back to DEFAULT_WEIGHTS.

    Returns
    -------
    List of OESScore, one per unique obs_level found in A2 fault rows.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    fault_a2 = df[(df["mode"] == "A2") & (df["scenario_group"] == "fault")].copy()
    if fault_a2.empty:
        return []

    levels = sorted(fault_a2["obs_level"].unique())

    # Per-level raw stats
    raw: Dict[str, Dict] = {}
    for lvl in levels:
        sub = fault_a2[fault_a2["obs_level"] == lvl]
        det_rate = float(sub["actual_detection"].mean()) if len(sub) else 0.0
        loc_rate = float(sub["actual_localization"].mean()) if len(sub) else 0.0

        ttd_vals = sub["time_to_detect_ms"].tolist() if "time_to_detect_ms" in sub else []
        speed = _speed_from_ttd(ttd_vals)

        # Cost: combine overhead_kb and variance_growth (both penalise)
        kb_vals = sub["resource_overhead_kb"].dropna().tolist() if "resource_overhead_kb" in sub else []
        var_vals = sub["variance_growth"].dropna().tolist() if "variance_growth" in sub else []
        mean_kb = float(np.mean(kb_vals)) if kb_vals else 0.0
        mean_var = float(np.mean(var_vals)) if var_vals else 1.0

        raw[lvl] = {
            "det_rate": det_rate,
            "loc_rate": loc_rate,
            "speed": speed,
            "mean_kb": mean_kb,
            "mean_var": mean_var,
            "n": len(sub),
        }

    # Normalise cost across levels so comparisons are fair
    all_kb = [raw[l]["mean_kb"] for l in levels]
    all_var = [raw[l]["mean_var"] for l in levels]
    norm_kb = _safe_norm(all_kb)
    norm_var = _safe_norm(all_var)
    # Combined cost = average of normalised kb and variance
    cost_scores = [(a + b) / 2 for a, b in zip(norm_kb, norm_var)]

    # Normalise speed scores across levels
    all_spd = [raw[l]["speed"] for l in levels]
    norm_spd = _safe_norm(all_spd)

    scores: List[OESScore] = []
    for i, lvl in enumerate(levels):
        r = raw[lvl]
        det  = r["det_rate"]
        loc  = r["loc_rate"]
        spd  = norm_spd[i]
        cst  = cost_scores[i]

        oes_val = (
            w["detection"]    * det
            + w["localization"] * loc
            + w["speed"]        * spd
            - w["cost"]         * cst
        )
        oes_val = max(0.0, min(1.0, oes_val))

        scores.append(OESScore(
            obs_level=lvl,
            detection_rate=det,
            localization_rate=loc,
            speed_score=spd,
            cost_score=cst,
            oes=oes_val,
            weights=dict(w),
            n=r["n"],
        ))

    return scores


def oes_dataframe(
    df: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Return OES scores as a DataFrame for tables and plots."""
    scores = compute_oes_scores(df, weights)
    if not scores:
        return pd.DataFrame()
    return pd.DataFrame([s.as_dict() for s in scores])


# ---------------------------------------------------------------------------
# Pareto frontier
# ---------------------------------------------------------------------------

def oes_pareto_frontier(oes_df: pd.DataFrame) -> pd.DataFrame:
    """Return points on the Pareto frontier (highest OES for lowest cost).

    A point is Pareto-efficient if no other point has both higher OES
    and lower cost_score.  Adds a boolean column ``pareto_efficient``.
    """
    if oes_df.empty or "oes" not in oes_df.columns or "cost_score" not in oes_df.columns:
        return oes_df

    result = oes_df.copy()
    efficient = []
    for i, row in result.iterrows():
        dominated = False
        for j, other in result.iterrows():
            if i == j:
                continue
            if other["oes"] >= row["oes"] and other["cost_score"] <= row["cost_score"]:
                if other["oes"] > row["oes"] or other["cost_score"] < row["cost_score"]:
                    dominated = True
                    break
        efficient.append(not dominated)
    result["pareto_efficient"] = efficient
    return result


# ---------------------------------------------------------------------------
# Sensitivity analysis
# ---------------------------------------------------------------------------

def oes_sensitivity(
    df: pd.DataFrame,
    weight_grid: Optional[List[Dict[str, float]]] = None,
) -> pd.DataFrame:
    """Run OES for multiple weight profiles to test robustness.

    Returns a DataFrame with columns: weight_profile, obs_level, oes.
    """
    if weight_grid is None:
        weight_grid = [
            {"detection": 0.45, "localization": 0.30, "speed": 0.15, "cost": 0.10},
            {"detection": 0.60, "localization": 0.20, "speed": 0.10, "cost": 0.10},
            {"detection": 0.40, "localization": 0.40, "speed": 0.10, "cost": 0.10},
            {"detection": 0.35, "localization": 0.25, "speed": 0.25, "cost": 0.15},
        ]

    rows = []
    for idx, w in enumerate(weight_grid):
        label = f"W{idx+1}: det={w['detection']:.0%} loc={w['localization']:.0%}"
        scores = compute_oes_scores(df, weights=w)
        for s in scores:
            rows.append({
                "weight_profile": label,
                "obs_level": s.obs_level,
                "oes": round(s.oes, 4),
            })
    return pd.DataFrame(rows)
