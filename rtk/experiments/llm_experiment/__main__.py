"""Entry point for the LLM-specific fault experiment.

Usage:
    cd rtk/
    python -m experiments.llm_experiment

Runs all 6 fault scenarios × 3 observability levels (18 combinations),
then prints the detection matrix and key findings.
"""

from __future__ import annotations

import asyncio
import sys
from typing import List

from experiments.observability.configs import ObservabilityLevel

from .faults import (
    LLMFaultClass,
    FAULT_REGISTRY,
    NormalProvider,
    UnavailableProvider,
    SlowProvider,
    NoToolCallsProvider,
    WrongToolProvider,
    WrongDiagnosticProvider,
)
from .runner import LLMFaultResult, run_scenario
from .report import print_results, format_markdown_table


OBS_LEVELS = [ObservabilityLevel.O0, ObservabilityLevel.O1, ObservabilityLevel.O2]

# Ordered list of scenarios to run
SCENARIOS: List[tuple] = [
    (LLMFaultClass.NORMAL, NormalProvider),
    (LLMFaultClass.LLM_UNAVAILABLE, UnavailableProvider),
    (LLMFaultClass.LLM_SLOW, lambda: SlowProvider(2000.0)),
    (LLMFaultClass.LLM_NO_TOOL_CALLS, NoToolCallsProvider),
    (LLMFaultClass.LLM_WRONG_TOOL, WrongToolProvider),
    (LLMFaultClass.LLM_WRONG_DIAGNOSTIC, WrongDiagnosticProvider),
]


async def main() -> None:
    print("LLM-specific fault experiment")
    print(f"Scenarios: {len(SCENARIOS)}  ×  Obs levels: {len(OBS_LEVELS)}")
    print()

    results: List[LLMFaultResult] = []

    for fault_class, provider_factory in SCENARIOS:
        _, description = FAULT_REGISTRY[fault_class]
        for obs_level in OBS_LEVELS:
            provider = provider_factory()
            result = await run_scenario(
                fault_name=fault_class.value,
                provider=provider,
                obs_level=obs_level,
                fault_description=description,
            )
            results.append(result)

            infra = "DETECTED   " if result.infra_detected else "not_detected"
            sem = "OK  " if result.semantic_ok else "FAIL"
            print(f"  [{obs_level.value}] {fault_class.value:<26}  infra={infra}  semantic={sem}")

    print_results(results)

    # Optionally write Markdown table for thesis
    if "--md" in sys.argv:
        md = format_markdown_table(results)
        print("--- Markdown table ---")
        print(md)
        print("--- end ---")


if __name__ == "__main__":
    asyncio.run(main())
