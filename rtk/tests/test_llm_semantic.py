"""Block B (extended) — Tests derived from LLM-specific experiment findings.

Each test class is explicitly linked to an LLM fault scenario result.
This file was created in Шаг 4 to codify the central finding:
two LLM fault classes (LLM_NO_TOOL_CALLS, LLM_WRONG_DIAGNOSTIC)
are completely invisible to O0/O1/O2 and require semantic validation.

Key experiment results that motivate this file:
  LLM_NO_TOOL_CALLS    infra=not_detected, semantic=FAIL → INVISIBLE
  LLM_WRONG_DIAGNOSTIC infra=not_detected, semantic=FAIL → INVISIBLE
  NORMAL               infra=not_detected, semantic=OK   → baseline

Run: pytest tests/test_llm_semantic.py -v -m experiment
"""

from __future__ import annotations

import asyncio
import time
import pytest

from common.models import ActionLogEntry
from experiments.observability.configs import ObservabilityLevel
from experiments.llm_experiment.semantic import SemanticChecker, EXPECTED_DIAGNOSTIC_TOOLS
from experiments.llm_experiment.faults import (
    NormalProvider,
    NoToolCallsProvider,
    WrongToolProvider,
    WrongDiagnosticProvider,
    SlowProvider,
    ORDER_ID,
)
from experiments.llm_experiment.runner import run_scenario


def _run(coro):
    """Run a coroutine synchronously (no pytest-asyncio needed)."""
    return asyncio.run(coro)


# ===================================================================
# SemanticChecker unit tests  (CHK-L-01, CHK-L-05)
# ===================================================================

class TestSemanticChecker:
    """Unit tests for SemanticChecker — the new detection layer.

    These tests validate that the semantic validator correctly identifies
    the two invisible fault classes: no-tool-calls and wrong-tool-calls.
    """

    @pytest.mark.experiment
    def test_empty_actions_fails(self):
        """CHK-L-01: empty action list → semantic check fails.

        Corresponds to LLM_NO_TOOL_CALLS: the agent produced no actions,
        which means no diagnostic tools were called.
        """
        checker = SemanticChecker()
        assert checker.check([]) is False

    @pytest.mark.experiment
    def test_correct_tool_passes(self):
        """CHK-L-05: get_order_status with ok=True → semantic check passes."""
        checker = SemanticChecker()
        actions = [
            ActionLogEntry(tool="get_order_status", params={"order_id": ORDER_ID}, ok=True)
        ]
        assert checker.check(actions) is True

    @pytest.mark.experiment
    def test_check_eissd_status_also_passes(self):
        """CHK-L-05 (variant): check_eissd_status is also an acceptable diagnostic tool."""
        checker = SemanticChecker()
        actions = [
            ActionLogEntry(tool="check_eissd_status", params={"order_id": ORDER_ID}, ok=True)
        ]
        assert checker.check(actions) is True

    @pytest.mark.experiment
    def test_wrong_tool_fails_even_if_ok(self):
        """CHK-L-03 (unit): list_otrs_comments with ok=True still fails semantic check.

        This is the core property of LLM_WRONG_DIAGNOSTIC:
        the tool call succeeded (entry.ok=True), so infrastructure monitoring
        sees nothing wrong — but the semantic layer correctly rejects it.
        """
        checker = SemanticChecker()
        actions = [
            ActionLogEntry(tool="list_otrs_comments", params={"ticket_id": "TKT-001"}, ok=True)
        ]
        assert checker.check(actions) is False

    @pytest.mark.experiment
    def test_failed_diagnostic_tool_does_not_pass(self):
        """Diagnostic tool called but ok=False must not count as correct behavior."""
        checker = SemanticChecker()
        actions = [
            ActionLogEntry(tool="get_order_status", params={"order_id": ORDER_ID}, ok=False,
                           error="Connection refused")
        ]
        assert checker.check(actions) is False

    @pytest.mark.experiment
    def test_expected_tools_set_is_correct(self):
        """EXPECTED_DIAGNOSTIC_TOOLS contains exactly the right tools."""
        assert "get_order_status" in EXPECTED_DIAGNOSTIC_TOOLS
        assert "check_eissd_status" in EXPECTED_DIAGNOSTIC_TOOLS
        assert "list_otrs_comments" not in EXPECTED_DIAGNOSTIC_TOOLS
        assert "phantom_diagnostic_tool" not in EXPECTED_DIAGNOSTIC_TOOLS

    @pytest.mark.experiment
    def test_describe_no_actions(self):
        checker = SemanticChecker()
        assert checker.describe([]) == "no_actions"

    @pytest.mark.experiment
    def test_describe_correct(self):
        checker = SemanticChecker()
        actions = [ActionLogEntry(tool="get_order_status", ok=True, params={})]
        assert "ok:" in checker.describe(actions)

    @pytest.mark.experiment
    def test_describe_wrong_tool(self):
        checker = SemanticChecker()
        actions = [ActionLogEntry(tool="list_otrs_comments", ok=True, params={})]
        assert "ok_but_wrong" in checker.describe(actions)


# ===================================================================
# Invisible fault integration tests  (CHK-L-02, CHK-L-03, CHK-L-04)
# ===================================================================

class TestInvisibleFaults:
    """Integration tests proving that invisible LLM faults are undetected by
    O0/O1/O2 but caught by the semantic layer.

    These are the central empirical results of the LLM-specific experiment.
    The tests encode the findings so they remain reproducible.
    """

    @pytest.mark.experiment
    def test_no_tool_calls_invisible_to_infra(self):
        """CHK-L-02: LLM_NO_TOOL_CALLS — O0 does NOT detect, semantic DOES detect.

        Experiment finding: NoToolCallsProvider → infra=not_detected, semantic=FAIL.
        Encodes the invisible fault at O0 level (minimal observability).
        """
        result = _run(run_scenario(
            fault_name="test_no_tool_calls",
            provider=NoToolCallsProvider(),
            obs_level=ObservabilityLevel.O0,
        ))
        assert result.infra_detected is False, (
            "LLM_NO_TOOL_CALLS must be invisible to O0 (no error counter fires). "
            "This is the key finding — changing this assertion means the fault "
            "became detectable, which would change the experiment conclusion."
        )
        assert result.semantic_ok is False, (
            "Semantic check must catch the missing diagnostic tools."
        )
        assert result.fallback_triggered is True

    @pytest.mark.experiment
    def test_no_tool_calls_invisible_to_o2(self):
        """CHK-L-02 (O2 variant): even the richest observability level misses it."""
        result = _run(run_scenario(
            fault_name="test_no_tool_calls_o2",
            provider=NoToolCallsProvider(),
            obs_level=ObservabilityLevel.O2,
        ))
        assert result.infra_detected is False, (
            "LLM_NO_TOOL_CALLS must be invisible even at O2 (span attributes + "
            "correlation + resources add no signal for a missing tool call)."
        )
        assert result.semantic_ok is False

    @pytest.mark.experiment
    def test_wrong_diagnostic_invisible_to_all_levels(self):
        """CHK-L-03: LLM_WRONG_DIAGNOSTIC — invisible to O0, O1, AND O2.

        The most dangerous finding: the agent calls a real, valid tool
        (list_otrs_comments) — the call succeeds, no errors, normal latency.
        All three observability levels report clean.  Only semantic catches it.
        """
        for obs_level in [ObservabilityLevel.O0, ObservabilityLevel.O1, ObservabilityLevel.O2]:
            result = _run(run_scenario(
                fault_name=f"test_wrong_diag_{obs_level.value}",
                provider=WrongDiagnosticProvider(),
                obs_level=obs_level,
            ))
            assert result.infra_detected is False, (
                f"[{obs_level.value}] LLM_WRONG_DIAGNOSTIC must be invisible to "
                f"infrastructure monitoring. Got: {result.signal_types}"
            )
            assert result.semantic_ok is False, (
                f"[{obs_level.value}] Semantic check must catch the wrong diagnostic."
            )

    @pytest.mark.experiment
    def test_wrong_diagnostic_action_appears_ok(self):
        """CHK-L-04: the wrong-diagnostic tool call has ok=True in the action log.

        This proves WHY the fault is invisible: from the infrastructure's
        perspective (error counters, logs, traces), the call succeeded.
        There is no error signal to detect.
        """
        result = _run(run_scenario(
            fault_name="test_wrong_diag_ok",
            provider=WrongDiagnosticProvider(),
            obs_level=ObservabilityLevel.O0,
        ))
        assert result.actions_count == 1
        assert result.actions_all_ok is True, (
            "The wrong-diagnostic action must appear ok=True — this is the "
            "mechanism that makes it invisible to O0/O1/O2."
        )
        assert result.semantic_ok is False


# ===================================================================
# Normal provider baseline  (CHK-L-05)
# ===================================================================

class TestNormalProviderBaseline:
    """Baseline: correct provider passes all checks.

    Ensures SemanticChecker and the runner don't produce false positives.
    """

    @pytest.mark.experiment
    def test_normal_provider_semantic_ok(self):
        """CHK-L-05: NormalProvider passes semantic check at all obs levels."""
        for obs_level in [ObservabilityLevel.O0, ObservabilityLevel.O1, ObservabilityLevel.O2]:
            result = _run(run_scenario(
                fault_name=f"test_normal_{obs_level.value}",
                provider=NormalProvider(),
                obs_level=obs_level,
            ))
            assert result.semantic_ok is True, (
                f"[{obs_level.value}] NormalProvider must pass semantic check."
            )
            assert result.actions_count >= 1
            assert result.infra_detected is False  # no fault injected → clean metrics

    @pytest.mark.experiment
    def test_normal_provider_calls_expected_tool(self):
        """NormalProvider must call get_order_status — the expected diagnostic tool."""
        result = _run(run_scenario(
            fault_name="test_normal_tool_check",
            provider=NormalProvider(),
            obs_level=ObservabilityLevel.O0,
        ))
        assert result.semantic_ok is True
        assert result.fallback_triggered is False


# ===================================================================
# LLM_SLOW: latency pattern mirrors BUG-007  (CHK-L-06)
# ===================================================================

class TestLLMSlowProvider:
    """CHK-L-06: SlowProvider latency pattern is consistent with BUG-007.

    BUG-007 showed infrastructure latency is invisible to O0, visible from O1.
    The LLM_SLOW case shows the same pattern at the LLM layer — methodologically
    consistent, which strengthens the experiment's conclusions.
    """

    @pytest.mark.experiment
    def test_llm_slow_invisible_to_o0(self):
        """LLM 2000ms latency — O0 (error counters only) does NOT detect it."""
        result = _run(run_scenario(
            fault_name="test_slow_o0",
            provider=SlowProvider(delay_ms=2000.0),
            obs_level=ObservabilityLevel.O0,
        ))
        assert result.infra_detected is False, (
            "Slow LLM must be invisible to O0. Mirrors BUG-007 pattern."
        )

    @pytest.mark.experiment
    def test_llm_slow_detectable_from_o1(self):
        """CHK-L-06: LLM 2000ms latency — O1 (latency histogram) DOES detect it."""
        result = _run(run_scenario(
            fault_name="test_slow_o1",
            provider=SlowProvider(delay_ms=2000.0),
            obs_level=ObservabilityLevel.O1,
        ))
        assert result.infra_detected is True, (
            "Slow LLM must be detectable at O1 via latency histogram. "
            "This mirrors BUG-007: the pattern is consistent across infra and LLM layers."
        )
        assert result.semantic_ok is True  # correct tool was still called

    @pytest.mark.experiment
    def test_llm_slow_semantic_still_passes(self):
        """Latency degradation does not affect diagnostic correctness.

        Even though the LLM is slow, it still calls the right tool.
        Semantic check must pass — latency is a performance issue, not a
        correctness issue.  This distinguishes it from the invisible faults.
        """
        result = _run(run_scenario(
            fault_name="test_slow_semantic",
            provider=SlowProvider(delay_ms=2000.0),
            obs_level=ObservabilityLevel.O2,
        ))
        assert result.semantic_ok is True


# ===================================================================
# LLM_WRONG_TOOL: detectable (contrast with invisible faults)
# ===================================================================

class TestWrongToolProvider:
    """LLM_WRONG_TOOL: hallucinated tool name → MCP error → O0 detects.

    This is the CONTRAST case that makes the invisible faults more striking:
    a hallucinated (non-existent) tool name raises a ValueError in the MCP
    client, which propagates as an error signal — detectable by O0.

    But if the LLM had chosen an EXISTING wrong tool (LLM_WRONG_DIAGNOSTIC),
    no error would have fired.  The difference is a single bit: tool exists or not.
    """

    @pytest.mark.experiment
    def test_wrong_tool_detected_by_o0(self):
        """Hallucinated tool name → MCP ValueError → O0 detects it."""
        result = _run(run_scenario(
            fault_name="test_wrong_tool_o0",
            provider=WrongToolProvider(),
            obs_level=ObservabilityLevel.O0,
        ))
        assert result.infra_detected is True, (
            "A non-existent tool name causes a MCP ValueError, which is an "
            "error signal detectable by O0.  Contrast: LLM_WRONG_DIAGNOSTIC "
            "uses an existing tool and is NOT detected."
        )
        assert result.semantic_ok is False

    @pytest.mark.experiment
    def test_wrong_tool_vs_wrong_diagnostic_detection_contrast(self):
        """Key contrast: non-existent tool detected, existing-wrong-tool invisible.

        This test encodes the most surprising finding of the LLM experiment:
        the difference between detectability and non-detectability is
        whether the tool NAME happens to exist in the MCP server.
        """
        wrong_tool_result = _run(run_scenario(
            "contrast_wrong_tool", WrongToolProvider(), ObservabilityLevel.O0
        ))
        wrong_diag_result = _run(run_scenario(
            "contrast_wrong_diag", WrongDiagnosticProvider(), ObservabilityLevel.O0
        ))

        # Non-existent tool → error → detected
        assert wrong_tool_result.infra_detected is True

        # Existing-but-wrong tool → no error → not detected
        assert wrong_diag_result.infra_detected is False

        # Both are semantically incorrect
        assert wrong_tool_result.semantic_ok is False
        assert wrong_diag_result.semantic_ok is False
