"""Block B — E2E / smoke tests.

End-to-end tests that exercise complete user scenarios via the FastAPI
TestClient. These require no external services (LLM, Ollama) — instead
they rely on the deterministic fallback mode.

Scenarios covered:
- Health check endpoint
- Metrics endpoint
- Full ticket intake (via mocked pipeline)
- Error handling for missing data
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from fastapi.testclient import TestClient

from agent_api.main import app, TicketIn
from common.models import ActionLogEntry


# ===================================================================
# FastAPI test client fixture
# ===================================================================

@pytest.fixture
def client():
    """Create a test client with a mocked MCP client."""
    mock_mcp = AsyncMock()
    app.state.mcp = mock_mcp
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ===================================================================
# Health & Metrics
# ===================================================================

class TestHealthEndpoint:
    @pytest.mark.e2e
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestMetricsEndpoint:
    @pytest.mark.e2e
    def test_metrics_returns_prometheus(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "agent_requests_total" in resp.text or "text/plain" in resp.headers.get("content-type", "")


# ===================================================================
# Ticket intake E2E with mocked pipeline
# ===================================================================

class TestTicketIntakeE2E:
    @pytest.mark.e2e
    def test_successful_intake(self, client):
        """Full E2E: ticket submitted → pipeline mocked → returns TicketOut."""
        mock_actions = [
            ActionLogEntry(tool="check_eissd_status", params={"order_id": "O1"}, ok=True)
        ]
        mock_verify = (
            {"sulz_db": {"status": "DONE"}, "eissd": {"status": "DONE"}, "_diag": []},
            [],
        )
        mock_comment = "RTK_AGENT_FINAL v1\nticket_id=T1\nnext_step=NO_ERROR_IN_LOGS\n"

        with patch("agent_api.main.precheck_logs", new_callable=AsyncMock) as m_pre, \
             patch("agent_api.main.call_rag", new_callable=AsyncMock) as m_rag, \
             patch("agent_api.main.plan_and_execute", new_callable=AsyncMock) as m_plan, \
             patch("agent_api.main.verify_final_status", new_callable=AsyncMock) as m_verify, \
             patch("agent_api.main.build_final_comment") as m_comment, \
             patch("agent_api.main.finalize", new_callable=AsyncMock) as m_finalize:

            m_pre.return_value = {"precheck": {"logs": {"error_found": False}}}
            m_rag.return_value = {"rag": None}
            m_plan.return_value = mock_actions
            m_verify.return_value = mock_verify
            m_comment.return_value = mock_comment
            m_finalize.return_value = []

            resp = client.post("/tickets/intake", json={
                "id": "T1",
                "order_id": "O1",
                "description": "Test order",
            })

            assert resp.status_code == 200
            data = resp.json()
            assert data["ticket_id"] == "T1"
            assert "RTK_AGENT_FINAL" in data["final_comment"]

    @pytest.mark.e2e
    def test_timeout_returns_504(self, client):
        """Pipeline timeout → HTTP 504."""
        with patch("agent_api.main.precheck_logs", new_callable=AsyncMock) as m_pre:
            m_pre.side_effect = TimeoutError("Budget exceeded")

            resp = client.post("/tickets/intake", json={
                "id": "T1",
                "order_id": "O1",
                "description": "desc",
            })
            assert resp.status_code == 504

    @pytest.mark.e2e
    def test_internal_error_returns_500(self, client):
        """Unexpected exception → HTTP 500."""
        with patch("agent_api.main.precheck_logs", new_callable=AsyncMock) as m_pre:
            m_pre.side_effect = RuntimeError("Unexpected")

            resp = client.post("/tickets/intake", json={
                "id": "T1",
                "order_id": "O1",
                "description": "desc",
            })
            assert resp.status_code == 500


class TestInputValidation:
    @pytest.mark.e2e
    def test_missing_required_field(self, client):
        """Missing 'id' → HTTP 422."""
        resp = client.post("/tickets/intake", json={
            "order_id": "O1",
            "description": "desc",
        })
        assert resp.status_code == 422

    @pytest.mark.e2e
    def test_empty_body(self, client):
        """Empty request body → HTTP 422."""
        resp = client.post("/tickets/intake", json={})
        assert resp.status_code == 422
