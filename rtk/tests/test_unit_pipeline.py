"""Block B — Unit tests for pipeline helper functions.

Tests deterministic pipeline logic:
- _unwrap_mcp_dict response normalisation
- build_final_comment template generation
- _ensure_budget timeout checking
"""

from __future__ import annotations

import time
import pytest
from datetime import datetime
from typing import Any, Dict, List

from common.models import ActionLogEntry, Ticket
from pipeline.pipeline import (
    _unwrap_mcp_dict,
    _as_error_dict,
    build_final_comment,
    _ensure_budget,
    PRECHECK_PATTERN,
    PRECHECK_WINDOW_DAYS,
)


@pytest.fixture
def ticket():
    return Ticket(
        id="TKT-001",
        order_id="ORD-123",
        subject="Test",
        annotation="ann",
        description="desc",
        region="MSK",
        queue="TestQueue",
        created_at=datetime(2025, 1, 1),
    )


# ===================================================================
# _unwrap_mcp_dict
# ===================================================================

class TestUnwrapMcpDict:
    @pytest.mark.unit
    def test_dict_passthrough(self):
        val, code, fatal = _unwrap_mcp_dict("tool", {"key": "value"})
        assert val == {"key": "value"}
        assert code is None
        assert fatal is False

    @pytest.mark.unit
    def test_list_single_dict(self):
        val, code, fatal = _unwrap_mcp_dict("tool", [{"key": "v"}])
        assert val == {"key": "v"}
        assert code is not None
        assert "list_to_dict" in code
        assert fatal is False

    @pytest.mark.unit
    def test_list_multi_dicts(self):
        val, code, fatal = _unwrap_mcp_dict("tool", [{"a": 1}, {"b": 2}])
        assert val == {"a": 1}
        assert "list_multi_dicts" in code
        assert fatal is False

    @pytest.mark.unit
    def test_list_no_dicts(self):
        val, code, fatal = _unwrap_mcp_dict("tool", ["str1", "str2"])
        assert fatal is True
        assert "list_no_dict" in code

    @pytest.mark.unit
    def test_unexpected_type(self):
        val, code, fatal = _unwrap_mcp_dict("tool", 42)
        assert fatal is True
        assert "bad_type" in code


class TestAsErrorDict:
    @pytest.mark.unit
    def test_structure(self):
        result = _as_error_dict("my_tool", [1, 2], "diag.code")
        assert result["error"] == "UNEXPECTED_MCP_RESPONSE"
        assert result["tool"] == "my_tool"
        assert result["diag"] == "diag.code"
        assert result["raw_type"] == "list"


# ===================================================================
# _ensure_budget
# ===================================================================

class TestEnsureBudget:
    @pytest.mark.unit
    def test_within_budget(self):
        _ensure_budget(time.monotonic() + 100)

    @pytest.mark.unit
    def test_exceeded(self):
        with pytest.raises(TimeoutError):
            _ensure_budget(time.monotonic() - 1)


# ===================================================================
# build_final_comment
# ===================================================================

class TestBuildFinalComment:
    @pytest.mark.unit
    def test_basic_structure(self, ticket):
        comment = build_final_comment(
            ticket,
            precheck={
                "logs": {
                    "error_found": True,
                    "error_code": "ORDER_STATUS_DENIED",
                    "logs_full": ["line1"],
                    "matched_samples": ["line1"],
                },
                "_diag": [],
            },
            rag={"required_actions": [{"tool": "a"}, {"tool": "b"}]},
            actions=[
                ActionLogEntry(tool="t1", params={}, ok=True),
                ActionLogEntry(tool="t2", params={}, ok=True),
            ],
            verify={
                "sulz_db": {"status": "DONE"},
                "eissd": {"status": "IN_PROGRESS"},
                "_diag": [],
            },
        )
        assert "RTK_AGENT_FINAL v1" in comment
        assert "ticket_id=TKT-001" in comment
        assert "order_id=ORD-123" in comment
        assert "region=MSK" in comment
        assert "precheck.error_found=true" in comment
        assert "rag.required_actions_count=2" in comment
        assert "actions.count=2" in comment
        assert "actions.ok=true" in comment
        assert "verify.sulz_db.status=DONE" in comment
        assert "verify.eissd.status=IN_PROGRESS" in comment
        assert "next_step=IN_WORK_WAIT_CONFIRMATION" in comment

    @pytest.mark.unit
    def test_no_error_next_step(self, ticket):
        comment = build_final_comment(
            ticket,
            precheck={"logs": {"error_found": False}, "_diag": []},
            rag=None,
            actions=[],
            verify={"sulz_db": None, "eissd": None, "_diag": []},
        )
        assert "next_step=NO_ERROR_IN_LOGS" in comment

    @pytest.mark.unit
    def test_failed_actions_escalate(self, ticket):
        comment = build_final_comment(
            ticket,
            precheck={
                "logs": {"error_found": True, "error_code": "X"},
                "_diag": [],
            },
            rag=None,
            actions=[ActionLogEntry(tool="t1", params={}, ok=False, error="fail")],
            verify={"_diag": []},
        )
        assert "next_step=ESCALATE_L2" in comment
        assert "actions.ok=false" in comment

    @pytest.mark.unit
    def test_diag_codes_included(self, ticket):
        comment = build_final_comment(
            ticket,
            precheck={"logs": {"error_found": False}, "_diag": ["diag.a"]},
            rag=None,
            actions=[],
            verify={"_diag": ["diag.b"]},
        )
        assert "diag.count=2" in comment
        assert "diag.0=diag.a" in comment
        assert "diag.1=diag.b" in comment

    @pytest.mark.unit
    def test_empty_precheck(self, ticket):
        comment = build_final_comment(
            ticket, precheck={}, rag=None, actions=[], verify={"_diag": []},
        )
        assert "precheck.error_found=false" in comment
        assert "next_step=NO_ERROR_IN_LOGS" in comment
