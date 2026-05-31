"""LLM-specific fault experiment runner.

For each (fault_type × observability_level) pair:
  1. Instantiate a mock LLM provider simulating the fault.
  2. Run a simplified planning loop instrumented by TelemetryCollector.
  3. Ask CombinedDetector whether the fault was detected via O0/O1/O2.
  4. Ask SemanticChecker whether the agent made the correct diagnostic decision.

The two detection methods are deliberately kept independent so that the
experiment can show which fault classes are invisible to infrastructure
monitoring and only catchable via semantic validation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from common.models import ActionLogEntry
from providers.base import BaseLLMProvider
from experiments.observability.configs import ObservabilityLevel, get_config
from experiments.observability.collectors import TelemetryCollector, SignalStore
from experiments.observability.detectors import CombinedDetector

from .mock_mcp import MockMCPClient
from .semantic import SemanticChecker


# In-memory service calls take ~0.1–0.5 ms.
# Latency detector fires when avg > baseline × 3.0, so threshold ≈ 0.3–1.5 ms.
# SlowProvider adds 2000 ms → well above threshold.
BASELINE_LATENCY_MS = 0.5

MAX_ITERATIONS = 5


@dataclass
class LLMFaultResult:
    fault_name: str
    obs_level: str
    fault_description: str = ""

    # Infrastructure detection (O0/O1/O2)
    infra_detected: bool = False
    signal_types: List[str] = field(default_factory=list)
    time_to_detect_ms: Optional[float] = None

    # Execution metadata
    actions_count: int = 0
    actions_all_ok: bool = False
    llm_error: bool = False
    fallback_triggered: bool = False

    # Semantic detection (new layer)
    semantic_ok: bool = False
    semantic_desc: str = ""


async def _planning_loop(
    provider: BaseLLMProvider,
    mock_mcp: MockMCPClient,
    collector: TelemetryCollector,
    order_id: str,
) -> Tuple[List[ActionLogEntry], bool, bool]:
    """Simplified planning loop with full telemetry instrumentation.

    Instruments both:
      - each LLM acall (captures LLM-level latency / errors)
      - each MCP tool call (captures tool-level errors)

    Returns (actions, fallback_triggered, llm_error).

    «fallback_triggered» is True when the LLM returned no tool calls and
    produced no actions — the real service would attempt a JSON-plan fallback,
    but for detection purposes the key finding is that O0/O1/O2 saw nothing.
    """
    tools_schema = mock_mcp.get_tools_schema()
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Ты агент диагностики заказов. "
                "Вызови нужные MCP tools и верни DONE когда закончишь."
            ),
        },
        {"role": "user", "content": f"Диагностируй заказ {order_id}"},
    ]

    actions: List[ActionLogEntry] = []
    llm_error = False

    for _ in range(MAX_ITERATIONS):
        # --- LLM call (instrumented) ---
        try:
            text, tool_calls = await collector.instrument_async_call(
                provider.acall,
                messages,
                tools_schema,
                timeout=30,
                call_name="llm_acall",
            )
        except Exception:
            llm_error = True
            break

        if not tool_calls:
            # No tool calls → planning done (or model gave up)
            break

        # Append assistant turn so context grows correctly on next iteration
        messages.append({"role": "assistant", "content": text or "", "tool_calls": tool_calls})

        # --- Execute each requested tool call (instrumented) ---
        for call in tool_calls:
            name = str(call.get("name") or "")
            params = call.get("arguments") or {}

            entry = ActionLogEntry(tool=name, params=dict(params))
            t0 = time.perf_counter()
            try:
                result = await collector.instrument_async_call(
                    mock_mcp.call_tool,
                    name,
                    params,
                    call_name=f"mcp_{name}",
                )
                entry.ok = True
                entry.result = result
            except Exception as exc:
                entry.ok = False
                entry.error = str(exc)
                entry.error_type = type(exc).__name__
            entry.duration_ms = int((time.perf_counter() - t0) * 1000)
            actions.append(entry)

            # Feed tool result back into conversation context
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": str(entry.result if entry.ok else entry.error),
            })

    fallback_triggered = not actions and not llm_error
    return actions, fallback_triggered, llm_error


async def run_scenario(
    fault_name: str,
    provider: BaseLLMProvider,
    obs_level: ObservabilityLevel,
    order_id: str = "1800003902272",
    fault_description: str = "",
) -> LLMFaultResult:
    """Run one (fault_type × obs_level) scenario and return the result."""
    config = get_config(obs_level)
    store = SignalStore()
    collector = TelemetryCollector(config, store)
    mock_mcp = MockMCPClient()
    checker = SemanticChecker()

    collector.begin_trace()
    actions, fallback, llm_error = await _planning_loop(
        provider, mock_mcp, collector, order_id
    )
    collector.end_trace()

    det = CombinedDetector().detect(store, baseline_latency_ms=BASELINE_LATENCY_MS)

    return LLMFaultResult(
        fault_name=fault_name,
        obs_level=obs_level.value,
        fault_description=fault_description,
        infra_detected=det.detected,
        signal_types=[s.value for s in det.signal_types_used],
        time_to_detect_ms=det.time_to_detect_ms,
        actions_count=len(actions),
        actions_all_ok=all(a.ok for a in actions) if actions else False,
        llm_error=llm_error,
        fallback_triggered=fallback,
        semantic_ok=checker.check(actions),
        semantic_desc=checker.describe(actions),
    )
