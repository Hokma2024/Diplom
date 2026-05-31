"""Comparison framework — Report generation."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .metrics import ExperimentResult


def generate_comparison_table(results: List[ExperimentResult]) -> List[Dict[str, Any]]:
    rows = []
    for r in results:
        s = r.summary()
        rows.append({
            "mode": s["mode"],
            "obs_level": s.get("obs_level", "—"),
            "defects_found": s["testing"]["defects_found"],
            "detection_rate": s["testing"]["detection_rate"],
            "exec_time_ms": s["testing"]["execution_time_ms"],
            "reproducibility": s["testing"]["reproducibility"],
            "fault_detected": s["diagnostic"]["detected"],
            "fault_localized": s["diagnostic"]["localized"],
            "ttd_ms": s["diagnostic"]["time_to_detect_ms"],
            "signal_usefulness": s["diagnostic"]["signal_usefulness"],
            "latency_oh_ms": s["overhead"]["latency_ms"],
            "latency_oh_pct": s["overhead"]["latency_pct"],
            "throughput_oh_pct": s["overhead"]["throughput_pct"],
            "variance_growth": s["overhead"]["variance_growth"],
            "exvivo_regressions": s["exvivo"]["regressions_found"],
            "exvivo_match_rate": s["exvivo"]["match_rate"],
        })
    return rows


def _fmt_overhead(row: Dict[str, Any]) -> str:
    """Format overhead line with a note when baseline is sub-millisecond.

    For in-memory services the baseline latency is in the microsecond range,
    making overhead% meaningless (any Python bookkeeping inflates the ratio).
    In those cases we report the absolute delta and flag the issue explicitly.
    """
    delta_ms = row["latency_oh_ms"]
    pct = row["latency_oh_pct"]
    tp = row["throughput_oh_pct"]
    vg = row["variance_growth"]

    # Heuristic: if overhead% > 200% the baseline is almost certainly sub-ms
    if abs(pct) > 200:
        return (
            f"latency_delta=+{delta_ms:.3f}ms "
            f"[overhead% N/A — in-memory baseline <1 ms, absolute delta is meaningful], "
            f"throughput_loss={tp:.1f}%, variance_growth={vg:.2f}x"
        )
    return (
        f"latency=+{delta_ms:.3f}ms ({pct:.1f}%), "
        f"throughput_loss={tp:.1f}%, variance_growth={vg:.2f}x"
    )


def generate_text_report(results: List[ExperimentResult]) -> str:
    lines = ["=" * 80, "EXPERIMENT COMPARISON REPORT", "=" * 80, ""]

    table = generate_comparison_table(results)
    for row in table:
        ttd = f"{row['ttd_ms']:.1f}" if row["ttd_ms"] is not None else "—"
        lines.append(f"Mode: {row['mode']} (obs={row['obs_level']})")
        lines.append(
            f"  Testing:    defects_found={row['defects_found']}, "
            f"detection_rate={row['detection_rate']:.1%}, "
            f"exec_time={row['exec_time_ms']:.1f}ms"
        )
        lines.append(
            f"  Monitoring: detected={row['fault_detected']}, "
            f"localized={row['fault_localized']}, "
            f"ttd={ttd}ms, "
            f"signal_usefulness={row['signal_usefulness']:.3f}"
        )
        lines.append(f"  Overhead:   {_fmt_overhead(row)}")
        lines.append(
            f"  Ex-vivo:    regressions={row['exvivo_regressions']}, "
            f"match_rate={row['exvivo_match_rate']:.1%}"
        )
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


def generate_json_report(results: List[ExperimentResult]) -> str:
    data = {
        "comparison_table": generate_comparison_table(results),
        "raw_summaries": [r.summary() for r in results],
    }
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)
