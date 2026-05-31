"""Results formatter for the LLM fault experiment.

Produces a concise summary table and a «Key findings» section
highlighting the invisible faults — the main thesis of the diploma.
"""

from __future__ import annotations

from typing import Dict, List

from .runner import LLMFaultResult

TICK = "✓"
CROSS = "✗"
DASH = "—"


def _yn(v: bool) -> str:
    return TICK if v else CROSS


def _ttd(ms: float | None) -> str:
    if ms is None:
        return DASH
    return f"{ms:.0f}ms"


def print_results(results: List[LLMFaultResult]) -> None:
    """Print the experiment matrix and key findings to stdout."""
    # Index by fault_name → obs_level
    by_fault: Dict[str, Dict[str, LLMFaultResult]] = {}
    for r in results:
        by_fault.setdefault(r.fault_name, {})[r.obs_level] = r

    col_w = 28
    print()
    print("=" * 80)
    print("  LLM-Specific Fault Experiment — Detection Matrix")
    print("=" * 80)
    print()
    print(f"  {'Fault scenario':<{col_w}}  {'O0':^5}  {'O1':^5}  {'O2':^5}  {'Sem':^5}  Actions  Notes")
    print(f"  {'-'*col_w}  {'─'*5}  {'─'*5}  {'─'*5}  {'─'*5}  {'─'*7}  {'─'*30}")

    invisible: List[str] = []

    for fault_name, by_level in by_fault.items():
        o0 = by_level.get("O0")
        o1 = by_level.get("O1")
        o2 = by_level.get("O2")
        ref = o0 or next(iter(by_level.values()))

        o0s = _yn(o0.infra_detected) if o0 else DASH
        o1s = _yn(o1.infra_detected) if o1 else DASH
        o2s = _yn(o2.infra_detected) if o2 else DASH
        sem = _yn(ref.semantic_ok)
        if ref.actions_count == 0:
            acts = "0  —"
        else:
            acts = f"{ref.actions_count} {'OK ' if ref.actions_all_ok else 'ERR'}"

        if ref.llm_error:
            notes = "LLM raised exception"
        elif ref.fallback_triggered:
            notes = "no tool calls → fallback"
        elif ref.actions_count > 0 and not ref.actions_all_ok:
            notes = f"tool error — {ref.semantic_desc}"
        elif ref.actions_count > 0 and not ref.semantic_ok:
            notes = f"wrong tool — {ref.semantic_desc}"
        else:
            notes = ref.semantic_desc

        print(
            f"  {fault_name:<{col_w}}  {o0s:^5}  {o1s:^5}  {o2s:^5}  "
            f"{sem:^5}  {acts:<7}  {notes}"
        )

        all_detected = all(
            r.infra_detected for r in by_level.values()
        )
        if not all_detected and not ref.semantic_ok:
            invisible.append(fault_name)

    print()
    print("  Legend:")
    print("    ✓ = detected   ✗ = not detected   Sem = semantic validation")
    print("    O0 = error counters + health only")
    print("    O1 = O0 + latency histograms + logs + traces")
    print("    O2 = O1 + span attributes + correlation + resources")
    print()

    if invisible:
        print("─" * 80)
        print("  *** INVISIBLE FAULTS — undetected by ALL observability levels ***")
        print()
        for name in invisible:
            ref_r = list(by_fault[name].values())[0]
            print(f"    • {name}")
            print(f"      {ref_r.fault_description}")
            print(f"      Semantic: {ref_r.semantic_desc}")
        print()
        print("  These fault classes require SEMANTIC validation to detect.")
        print("  This is the central finding of the LLM-agent testing experiment.")
        print("─" * 80)
    else:
        print("  All faults were detected by at least one observability level.")

    print()


def format_markdown_table(results: List[LLMFaultResult]) -> str:
    """Return a Markdown table for inclusion in the thesis text."""
    by_fault: Dict[str, Dict[str, LLMFaultResult]] = {}
    for r in results:
        by_fault.setdefault(r.fault_name, {})[r.obs_level] = r

    lines = [
        "| Сценарий | O0 | O1 | O2 | Семантика | Действий | Примечание |",
        "|---|:---:|:---:|:---:|:---:|:---:|---|",
    ]
    for fault_name, by_level in by_fault.items():
        o0 = by_level.get("O0")
        o1 = by_level.get("O1")
        o2 = by_level.get("O2")
        ref = o0 or next(iter(by_level.values()))

        o0s = "✓" if (o0 and o0.infra_detected) else "✗"
        o1s = "✓" if (o1 and o1.infra_detected) else "✗"
        o2s = "✓" if (o2 and o2.infra_detected) else "✗"
        sem = "✓" if ref.semantic_ok else "✗"
        acts = str(ref.actions_count)

        if ref.llm_error:
            note = "исключение LLM"
        elif ref.fallback_triggered:
            note = "нет вызовов tool"
        elif not ref.semantic_ok and ref.actions_count > 0:
            note = "неверный tool"
        else:
            note = ""

        lines.append(f"| {fault_name} | {o0s} | {o1s} | {o2s} | {sem} | {acts} | {note} |")

    return "\n".join(lines)
