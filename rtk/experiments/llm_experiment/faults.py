"""Mock LLM providers for LLM-specific fault injection.

Each class simulates a distinct fault class that can occur in
a real LLM-based agent (Ollama/OpenRouter), without needing
an actual LLM connection.

Design note: all providers implement BaseLLMProvider.acall so they
are drop-in replacements inside the experiment planning loop.
"""

from __future__ import annotations

import asyncio
import enum
from typing import Any, Dict, List, Tuple

from providers.base import BaseLLMProvider

# Order used in all scenarios — matches the in-memory storage seed.
ORDER_ID = "1800003902272"
TICKET_ID = "TKT-001"

Calls = List[Dict[str, Any]]


class LLMFaultClass(str, enum.Enum):
    NORMAL = "NORMAL"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_SLOW = "LLM_SLOW"
    LLM_NO_TOOL_CALLS = "LLM_NO_TOOL_CALLS"
    LLM_WRONG_TOOL = "LLM_WRONG_TOOL"
    LLM_WRONG_DIAGNOSTIC = "LLM_WRONG_DIAGNOSTIC"


class NormalProvider(BaseLLMProvider):
    """Baseline: calls get_order_status once, then returns DONE."""

    def __init__(self) -> None:
        self._iter = 0

    async def acall(
        self, messages: list, tools: list, *, timeout: int
    ) -> Tuple[str, Calls]:
        self._iter += 1
        if self._iter == 1:
            return "", [{"name": "get_order_status", "arguments": {"order_id": ORDER_ID}}]
        return "DONE", []


class UnavailableProvider(BaseLLMProvider):
    """LLM provider is down — raises ConnectionError on every call.

    Expected: O0 detects (error counter fires), O1/O2 also detect.
    Semantic: no actions → FAIL.
    """

    async def acall(
        self, messages: list, tools: list, *, timeout: int
    ) -> Tuple[str, Calls]:
        raise ConnectionError("LLM provider unavailable (connection refused)")


class SlowProvider(BaseLLMProvider):
    """LLM response is delayed by delay_ms milliseconds before returning.

    Expected: O0 does NOT detect (no error), O1/O2 detect latency spike.
    Semantic: correct tool called → PASS.
    """

    def __init__(self, delay_ms: float = 2000.0) -> None:
        self._delay_s = delay_ms / 1000.0
        self._iter = 0

    async def acall(
        self, messages: list, tools: list, *, timeout: int
    ) -> Tuple[str, Calls]:
        await asyncio.sleep(self._delay_s)
        self._iter += 1
        if self._iter == 1:
            return "", [{"name": "get_order_status", "arguments": {"order_id": ORDER_ID}}]
        return "DONE", []


class NoToolCallsProvider(BaseLLMProvider):
    """LLM never calls any tools — returns only text.

    The model "answered" without using any MCP tools.  This is a quality
    degradation: from the infrastructure's point of view nothing went wrong
    (no exception, normal latency), but the agent skipped all diagnostics.

    Expected: O0/O1/O2 all FAIL to detect.
    Semantic: no actions → FAIL.
    """

    async def acall(
        self, messages: list, tools: list, *, timeout: int
    ) -> Tuple[str, Calls]:
        return "DONE", []


class WrongToolProvider(BaseLLMProvider):
    """LLM calls a hallucinated (non-existent) tool name.

    The MCP call will fail with ValueError → error signals ARE emitted.
    This is detectable by O0, unlike the pure quality-degradation cases.

    One-shot: after the tool error the model returns DONE (realistic —
    a real LLM would see the error result and stop).

    Expected: O0/O1/O2 detect (tool call error).
    Semantic: no valid action → FAIL.
    """

    def __init__(self) -> None:
        self._iter = 0

    async def acall(
        self, messages: list, tools: list, *, timeout: int
    ) -> Tuple[str, Calls]:
        self._iter += 1
        if self._iter == 1:
            # Hallucinated tool name — does not exist in MCP server
            return "", [{"name": "phantom_diagnostic_tool", "arguments": {"order_id": ORDER_ID}}]
        return "DONE", []


class WrongDiagnosticProvider(BaseLLMProvider):
    """LLM calls a valid tool, but the wrong one for this diagnostic task.

    Uses list_otrs_comments (comments listing) instead of get_order_status.
    The MCP call SUCCEEDS — no exception, normal latency, ok=True.
    But the agent diagnosed the wrong dimension of the problem.

    This is the central «invisible fault» case of the experiment:
    O0/O1/O2 all show clean signals, yet the diagnosis is incorrect.

    Expected: O0/O1/O2 all FAIL to detect.
    Semantic: expected diagnostic tool never called → FAIL.
    """

    def __init__(self) -> None:
        self._iter = 0

    async def acall(
        self, messages: list, tools: list, *, timeout: int
    ) -> Tuple[str, Calls]:
        self._iter += 1
        if self._iter == 1:
            # list_otrs_comments is a real, valid MCP tool.
            # It will succeed and return an empty comment list.
            # No exception will be raised — everything looks healthy.
            return "", [{"name": "list_otrs_comments", "arguments": {"ticket_id": TICKET_ID}}]
        return "DONE", []


# Registry: fault class → (provider_factory, description)
FAULT_REGISTRY: Dict[LLMFaultClass, Tuple[Any, str]] = {
    LLMFaultClass.NORMAL: (
        NormalProvider,
        "Baseline — LLM calls get_order_status correctly",
    ),
    LLMFaultClass.LLM_UNAVAILABLE: (
        UnavailableProvider,
        "LLM provider down — ConnectionError on every acall",
    ),
    LLMFaultClass.LLM_SLOW: (
        lambda: SlowProvider(2000.0),
        "LLM latency degradation — 2000ms delay before each response",
    ),
    LLMFaultClass.LLM_NO_TOOL_CALLS: (
        NoToolCallsProvider,
        "LLM returns text only — zero tool calls, agent skips all diagnostics",
    ),
    LLMFaultClass.LLM_WRONG_TOOL: (
        WrongToolProvider,
        "LLM calls non-existent tool — MCP raises ValueError",
    ),
    LLMFaultClass.LLM_WRONG_DIAGNOSTIC: (
        WrongDiagnosticProvider,
        "LLM calls wrong valid tool — succeeds but wrong diagnosis",
    ),
}
