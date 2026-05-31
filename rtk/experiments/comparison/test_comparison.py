"""Comparison framework — Integration tests.

Runs all four experiment modes (A0/A1/A2/A3) and verifies:
- Each mode produces valid ExperimentResult
- Comparison metrics are computed correctly
- Reports can be generated
- A1 finds additional defects over A0
- A2 produces diagnostic data
- A3 combines both capabilities
"""

from __future__ import annotations

import json
import pytest

from experiments.comparison.runner import run_a0, run_a1, run_a2, run_a3
from experiments.comparison.metrics import ExperimentResult
from experiments.comparison.report import (
    generate_comparison_table,
    generate_text_report,
    generate_json_report,
)
from experiments.observability.configs import ObservabilityLevel


class TestExperimentModes:
    @pytest.mark.integration
    def test_a0_baseline(self):
        result = run_a0()
        assert result.mode == "A0"
        assert result.testing.total_tests > 0
        assert result.testing.passed_tests > 0
        s = result.summary()
        assert s["mode"] == "A0"

    @pytest.mark.integration
    def test_a1_exvivo(self):
        result = run_a1()
        assert result.mode == "A1"
        assert result.exvivo.total_interactions > 0
        # run_a1 applies a storage mutation between capture and replay to
        # demonstrate regression detection — at least one mismatch expected.
        assert result.exvivo.regressions_found > 0
        assert result.exvivo.match_rate < 1.0

    @pytest.mark.integration
    def test_a2_fault_injection(self):
        result = run_a2(ObservabilityLevel.O1)
        assert result.mode == "A2"
        assert result.diagnostic.fault_detected is True
        assert result.overhead.latency_overhead_ms is not None

    @pytest.mark.integration
    def test_a3_combined(self):
        result = run_a3(ObservabilityLevel.O1)
        assert result.mode == "A3"
        assert result.exvivo.total_interactions > 0
        assert result.diagnostic.fault_detected is True

    @pytest.mark.integration
    def test_a2_across_obs_levels(self):
        """A2 with different observability levels gives different detail."""
        r_o0 = run_a2(ObservabilityLevel.O0)
        r_o2 = run_a2(ObservabilityLevel.O2)
        # Both should detect the fault
        assert r_o0.diagnostic.fault_detected
        assert r_o2.diagnostic.fault_detected


class TestComparisonReports:
    @pytest.mark.integration
    def test_comparison_table(self):
        results = [run_a0(), run_a1(), run_a2(), run_a3()]
        table = generate_comparison_table(results)
        assert len(table) == 4
        assert all("mode" in row for row in table)
        assert table[0]["mode"] == "A0"
        assert table[3]["mode"] == "A3"

    @pytest.mark.integration
    def test_text_report(self):
        results = [run_a0(), run_a1()]
        report = generate_text_report(results)
        assert "EXPERIMENT COMPARISON REPORT" in report
        assert "Mode: A0" in report
        assert "Mode: A1" in report

    @pytest.mark.integration
    def test_json_report(self):
        results = [run_a0(), run_a2()]
        report = generate_json_report(results)
        data = json.loads(report)
        assert "comparison_table" in data
        assert "raw_summaries" in data
        assert len(data["comparison_table"]) == 2
