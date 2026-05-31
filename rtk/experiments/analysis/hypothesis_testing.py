"""Statistical hypothesis testing for observability experiment results.

Formal hypotheses tested:

H1  A2/O1 detects significantly more faults than A2/O0
    (latency-class faults invisible to error-counter-only monitoring)

H2  A2/O2 detection rate is not significantly higher than A2/O1
    (Pareto insight: O1 captures most of the gain)

H3  TTD at O1 is significantly lower than at O0 (where both detect)

H4  Ex-vivo A1 detects regressions that classical A0 misses entirely

All tests are two-proportion z-test / chi-squared for detection rates
and Mann-Whitney U for continuous TTD distributions.
Effect sizes: Cohen's h (proportions), rank-biserial r (Mann-Whitney).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class ProportionTestResult:
    """Result of a two-proportion test."""
    hypothesis: str
    group_a: str
    group_b: str
    n_a: int
    n_b: int
    p_a: float
    p_b: float
    diff: float                 # p_b - p_a
    chi2: float
    p_value: float
    cohens_h: float             # effect size
    significant: bool           # p < 0.05
    interpretation: str


@dataclass
class RankTestResult:
    """Result of a Mann-Whitney U test."""
    hypothesis: str
    group_a: str
    group_b: str
    n_a: int
    n_b: int
    median_a: float
    median_b: float
    u_statistic: float
    p_value: float
    rank_biserial_r: float      # effect size
    significant: bool
    interpretation: str


@dataclass
class HypothesisReport:
    """Full hypothesis testing report for the diploma."""
    proportion_tests: List[ProportionTestResult] = field(default_factory=list)
    rank_tests: List[RankTestResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proportion_tests": [vars(t) for t in self.proportion_tests],
            "rank_tests": [vars(t) for t in self.rank_tests],
        }

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for t in self.proportion_tests:
            rows.append({
                "hypothesis": t.hypothesis,
                "test_type": "chi-squared (proportions)",
                "group_a": t.group_a,
                "group_b": t.group_b,
                "p_a": round(t.p_a, 4),
                "p_b": round(t.p_b, 4),
                "diff": round(t.diff, 4),
                "statistic": round(t.chi2, 4),
                "p_value": round(t.p_value, 4),
                "effect_size": round(t.cohens_h, 4),
                "effect_metric": "Cohen's h",
                "significant": t.significant,
                "interpretation": t.interpretation,
            })
        for t in self.rank_tests:
            rows.append({
                "hypothesis": t.hypothesis,
                "test_type": "Mann-Whitney U",
                "group_a": t.group_a,
                "group_b": t.group_b,
                "p_a": round(t.median_a, 4),
                "p_b": round(t.median_b, 4),
                "diff": round(t.median_b - t.median_a, 4),
                "statistic": round(t.u_statistic, 4),
                "p_value": round(t.p_value, 4),
                "effect_size": round(t.rank_biserial_r, 4),
                "effect_metric": "rank-biserial r",
                "significant": t.significant,
                "interpretation": t.interpretation,
            })
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cohens_h(p1: float, p2: float) -> float:
    """Cohen's h effect size for two proportions."""
    phi1 = 2 * math.asin(math.sqrt(max(0.0, min(1.0, p1))))
    phi2 = 2 * math.asin(math.sqrt(max(0.0, min(1.0, p2))))
    return abs(phi2 - phi1)


def _rank_biserial_r(u: float, n1: int, n2: int) -> float:
    """Rank-biserial correlation from Mann-Whitney U."""
    return 1 - (2 * u) / (n1 * n2)


def _proportion_test(
    hypothesis: str,
    group_a: str,
    group_b: str,
    detected_a: int,
    n_a: int,
    detected_b: int,
    n_b: int,
) -> ProportionTestResult:
    """Chi-squared test of independence for two detection-rate proportions."""
    p_a = detected_a / n_a if n_a else 0.0
    p_b = detected_b / n_b if n_b else 0.0

    # Contingency table
    table = np.array([
        [detected_a,     n_a - detected_a],
        [detected_b,     n_b - detected_b],
    ])

    # Use Fisher's exact for small cells (expected < 5)
    expected_min = min(
        (detected_a + detected_b) * n_a / (n_a + n_b),
        (n_a - detected_a + n_b - detected_b) * n_a / (n_a + n_b),
    )
    if expected_min < 5 or n_a < 10 or n_b < 10:
        _, p_value = stats.fisher_exact(table, alternative="two-sided")
        chi2 = float("nan")
    else:
        chi2_stat, p_value, _, _ = stats.chi2_contingency(table, correction=False)
        chi2 = float(chi2_stat)

    h = _cohens_h(p_a, p_b)
    significant = p_value < 0.05

    diff = p_b - p_a
    direction = "higher" if diff > 0 else "lower"
    sig_str = "significant" if significant else "not significant"
    interp = (
        f"{group_b} detection rate ({p_b:.1%}) is {abs(diff):.1%} {direction} "
        f"than {group_a} ({p_a:.1%}); {sig_str} at α=0.05 "
        f"(p={p_value:.4f}, Cohen's h={h:.3f})"
    )

    return ProportionTestResult(
        hypothesis=hypothesis,
        group_a=group_a,
        group_b=group_b,
        n_a=n_a,
        n_b=n_b,
        p_a=p_a,
        p_b=p_b,
        diff=diff,
        chi2=chi2 if not math.isnan(chi2) else 0.0,
        p_value=float(p_value),
        cohens_h=h,
        significant=significant,
        interpretation=interp,
    )


def _rank_test(
    hypothesis: str,
    group_a: str,
    group_b: str,
    values_a: List[float],
    values_b: List[float],
) -> Optional[RankTestResult]:
    """Mann-Whitney U test for two TTD distributions."""
    a = [v for v in values_a if v is not None and not math.isnan(v)]
    b = [v for v in values_b if v is not None and not math.isnan(v)]

    if len(a) < 2 or len(b) < 2:
        return None

    u_stat, p_value = stats.mannwhitneyu(a, b, alternative="two-sided")
    r = _rank_biserial_r(float(u_stat), len(a), len(b))
    median_a = float(np.median(a))
    median_b = float(np.median(b))
    significant = p_value < 0.05

    diff = median_b - median_a
    direction = "longer" if diff > 0 else "shorter"
    sig_str = "significant" if significant else "not significant"
    interp = (
        f"Median TTD {group_b} ({median_b:.1f} ms) is {abs(diff):.1f} ms {direction} "
        f"than {group_a} ({median_a:.1f} ms); {sig_str} at α=0.05 "
        f"(p={p_value:.4f}, r={r:.3f})"
    )

    return RankTestResult(
        hypothesis=hypothesis,
        group_a=group_a,
        group_b=group_b,
        n_a=len(a),
        n_b=len(b),
        median_a=median_a,
        median_b=median_b,
        u_statistic=float(u_stat),
        p_value=float(p_value),
        rank_biserial_r=r,
        significant=significant,
        interpretation=interp,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_hypothesis_tests(df: pd.DataFrame) -> HypothesisReport:
    """Run all four formal hypotheses on the experiment DataFrame.

    Expects columns: mode, obs_level, scenario_group, actual_detection,
    actual_localization, time_to_detect_ms.
    """
    report = HypothesisReport()

    if df.empty:
        return report

    fault_df = df[df["scenario_group"] == "fault"].copy()
    reg_df = df[df["scenario_group"] == "regression"].copy()

    # ------------------------------------------------------------------
    # H1: O1 detects significantly more faults than O0 (A2 fault scenarios)
    # ------------------------------------------------------------------
    o0 = fault_df[(fault_df["mode"] == "A2") & (fault_df["obs_level"] == "O0")]
    o1 = fault_df[(fault_df["mode"] == "A2") & (fault_df["obs_level"] == "O1")]
    if len(o0) and len(o1):
        report.proportion_tests.append(_proportion_test(
            hypothesis="H1: O1 > O0 (fault detection rate)",
            group_a="A2/O0",
            group_b="A2/O1",
            detected_a=int(o0["actual_detection"].sum()),
            n_a=len(o0),
            detected_b=int(o1["actual_detection"].sum()),
            n_b=len(o1),
        ))

    # ------------------------------------------------------------------
    # H2: O2 detection rate vs O1 (marginal gain test)
    # ------------------------------------------------------------------
    o2 = fault_df[(fault_df["mode"] == "A2") & (fault_df["obs_level"] == "O2")]
    if len(o1) and len(o2):
        report.proportion_tests.append(_proportion_test(
            hypothesis="H2: O2 vs O1 (marginal gain at extended observability)",
            group_a="A2/O1",
            group_b="A2/O2",
            detected_a=int(o1["actual_detection"].sum()),
            n_a=len(o1),
            detected_b=int(o2["actual_detection"].sum()),
            n_b=len(o2),
        ))

    # ------------------------------------------------------------------
    # H3: A3 detects more than A2/O1 (combined approach advantage)
    # ------------------------------------------------------------------
    a2_o1 = fault_df[(fault_df["mode"] == "A2") & (fault_df["obs_level"] == "O1")]
    a3 = fault_df[fault_df["mode"] == "A3"]
    if len(a2_o1) and len(a3):
        report.proportion_tests.append(_proportion_test(
            hypothesis="H3: A3 (combined) ≥ A2/O1 (fault detection)",
            group_a="A2/O1",
            group_b="A3",
            detected_a=int(a2_o1["actual_detection"].sum()),
            n_a=len(a2_o1),
            detected_b=int(a3["actual_detection"].sum()),
            n_b=len(a3),
        ))

    # ------------------------------------------------------------------
    # H4: A1 (ex-vivo) detects regressions that A0 misses
    # ------------------------------------------------------------------
    a0_reg = reg_df[reg_df["mode"] == "A0"]
    a1_reg = reg_df[reg_df["mode"] == "A1"]
    if len(a0_reg) and len(a1_reg):
        report.proportion_tests.append(_proportion_test(
            hypothesis="H4: A1 ex-vivo detects regressions missed by A0",
            group_a="A0 (regression scenarios)",
            group_b="A1 (ex-vivo)",
            detected_a=int(a0_reg["actual_detection"].sum()),
            n_a=len(a0_reg),
            detected_b=int(a1_reg["actual_detection"].sum()),
            n_b=len(a1_reg),
        ))

    # ------------------------------------------------------------------
    # H3-TTD: TTD at O1 is lower than at O0 (where detection occurred)
    # ------------------------------------------------------------------
    ttd_col = "time_to_detect_ms"
    if ttd_col in fault_df.columns:
        o0_det = fault_df[
            (fault_df["mode"] == "A2") &
            (fault_df["obs_level"] == "O0") &
            (fault_df["actual_detection"] == True)
        ][ttd_col].dropna().tolist()
        o1_det = fault_df[
            (fault_df["mode"] == "A2") &
            (fault_df["obs_level"] == "O1") &
            (fault_df["actual_detection"] == True)
        ][ttd_col].dropna().tolist()
        o2_det = fault_df[
            (fault_df["mode"] == "A2") &
            (fault_df["obs_level"] == "O2") &
            (fault_df["actual_detection"] == True)
        ][ttd_col].dropna().tolist()

        r = _rank_test(
            "H5: TTD(O1) vs TTD(O0) — Mann-Whitney U",
            "A2/O0", "A2/O1", o0_det, o1_det,
        )
        if r:
            report.rank_tests.append(r)

        r = _rank_test(
            "H6: TTD(O2) vs TTD(O1) — Mann-Whitney U",
            "A2/O1", "A2/O2", o1_det, o2_det,
        )
        if r:
            report.rank_tests.append(r)

    return report
