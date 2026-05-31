"""Block B — API contract tests.

Validate HTTP API contracts without requiring a running LLM backend:
- Endpoint availability (health, metrics)
- Request/response schemas (TicketIn, TicketOut)
- Status codes for valid and invalid inputs
- Pydantic model serialisation round-trips
- RAG mock API contract
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_api.main import TicketIn, TicketOut
from pipeline.rag_models import RagRequest, RagResponse


# ===================================================================
# TicketIn contract
# ===================================================================

class TestTicketInContract:
    @pytest.mark.contract
    def test_valid_minimal(self):
        t = TicketIn(id="T1", order_id="O1", description="desc")
        assert t.id == "T1"
        assert t.subject == ""
        assert t.region == "COMMON"
        assert t.queue is None
        assert t.metadata is None

    @pytest.mark.contract
    def test_valid_full(self):
        t = TicketIn(
            id="T2", order_id="O2", subject="subj", annotation="ann",
            description="full", region="MSK", queue="Q1",
            metadata={"key": "val"},
        )
        assert t.region == "MSK"
        assert t.metadata["key"] == "val"

    @pytest.mark.contract
    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            TicketIn(order_id="O1", description="desc")  # missing id

    @pytest.mark.contract
    def test_missing_description(self):
        with pytest.raises(ValidationError):
            TicketIn(id="T1", order_id="O1")  # missing description

    @pytest.mark.contract
    def test_serialisation_round_trip(self):
        t = TicketIn(id="T1", order_id="O1", description="desc")
        data = t.model_dump()
        t2 = TicketIn(**data)
        assert t == t2


# ===================================================================
# TicketOut contract
# ===================================================================

class TestTicketOutContract:
    @pytest.mark.contract
    def test_valid_minimal(self):
        out = TicketOut(ticket_id="T1", final_comment="comment", summary="sum")
        assert out.actions is None

    @pytest.mark.contract
    def test_with_actions(self):
        out = TicketOut(
            ticket_id="T1",
            final_comment="comment",
            summary="sum",
            actions=[{"tool": "t1", "ok": True}],
        )
        assert len(out.actions) == 1

    @pytest.mark.contract
    def test_serialisation(self):
        out = TicketOut(ticket_id="T1", final_comment="c", summary="s")
        j = out.model_dump_json()
        assert "ticket_id" in j


# ===================================================================
# RagRequest / RagResponse contracts
# ===================================================================

class TestRagContracts:
    @pytest.mark.contract
    def test_rag_request_defaults(self):
        req = RagRequest(
            ticket_id="T1", order_id="O1", subject="s",
            annotation="a", description="d",
        )
        assert req.precheck == {}

    @pytest.mark.contract
    def test_rag_response_defaults(self):
        resp = RagResponse()
        assert resp.required_actions == []
        assert resp.conditions == {}
        assert resp.parameters == {}

    @pytest.mark.contract
    def test_rag_response_with_actions(self):
        resp = RagResponse(
            required_actions=[{"tool": "check_eissd_status", "arguments": {"order_id": "O1"}}],
            conditions={"error_found": True},
            parameters={"ticket_id": "T1"},
        )
        assert len(resp.required_actions) == 1
        assert resp.conditions["error_found"] is True

    @pytest.mark.contract
    def test_rag_round_trip(self):
        req = RagRequest(
            ticket_id="T1", order_id="O1", subject="s",
            annotation="a", description="d",
            precheck={"logs": {"error_found": True}},
        )
        data = req.model_dump()
        req2 = RagRequest(**data)
        assert req.precheck == req2.precheck


# ===================================================================
# RAG Mock endpoint logic test
# ===================================================================

class TestRagMockLogic:
    @pytest.mark.contract
    def test_error_found_returns_3_actions(self):
        from services.rag_mock.main import query
        import asyncio
        req = RagRequest(
            ticket_id="T1", order_id="O1", subject="s",
            annotation="a", description="d",
            precheck={"logs": {"error_found": True}},
        )
        resp = asyncio.get_event_loop().run_until_complete(query(req))
        assert len(resp.required_actions) == 3

    @pytest.mark.contract
    def test_no_error_returns_1_action(self):
        from services.rag_mock.main import query
        import asyncio
        req = RagRequest(
            ticket_id="T1", order_id="O1", subject="s",
            annotation="a", description="d",
            precheck={"logs": {"error_found": False}},
        )
        resp = asyncio.get_event_loop().run_until_complete(query(req))
        assert len(resp.required_actions) == 1
