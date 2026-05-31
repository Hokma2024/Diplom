"""Block B — Integration tests for service interactions.

Tests interactions between components without mocking:
- OrderService ↔ storage interactions
- OtrsService ↔ storage interactions
- Cross-service workflows (search → update → verify)
- State consistency after multi-step operations
"""

from __future__ import annotations

import pytest
from services.mcp_server.models import (
    OrderStatus,
    OtrsStatus,
    SearchLogsRequest,
    GetOrderStatusRequest,
    CheckEissdStatusRequest,
    UpdateOrderStatusRequest,
    AddOtrsCommentRequest,
    ListOtrsCommentsRequest,
    GetOtrsTicketRequest,
    UpdateOtrsTicketRequest,
    ResolveMrfQueueRequest,
    CheckEditOrderRequest,
    CheckEditOrderResponse,
)
from services.mcp_server.services import OrderService, OtrsService
from services.mcp_server import storage


class TestCrossServiceWorkflow:
    """Integration: search logs → update order → verify new status."""

    @pytest.mark.integration
    def test_denied_order_workflow(self):
        order_id = "1800003902272"

        # Step 1: search logs finds error
        search = OrderService.search_logs(
            SearchLogsRequest(order_id=order_id, pattern="ORDER_STATUS_DENIED")
        )
        assert search.error_found is True

        # Step 2: check current status
        status = OrderService.get_order_status(GetOrderStatusRequest(order_id=order_id))
        assert status.status == OrderStatus.DENIED

        # Step 3: check EISSD
        eissd = OrderService.check_eissd_status(CheckEissdStatusRequest(order_id=order_id))
        assert eissd.status == OrderStatus.IN_PROGRESS

        # Step 4: update order status
        update = OrderService.update_order_status(
            UpdateOrderStatusRequest(order_id=order_id, new_status=OrderStatus.IN_PROGRESS)
        )
        assert update.updated is True
        assert update.old_status == OrderStatus.DENIED

        # Step 5: verify status changed
        new_status = OrderService.get_order_status(GetOrderStatusRequest(order_id=order_id))
        assert new_status.status == OrderStatus.IN_PROGRESS

    @pytest.mark.integration
    def test_otrs_ticket_lifecycle(self):
        ticket_id = "TKT-INT-001"

        # Step 1: get ticket (default)
        t = OtrsService.get_ticket(GetOtrsTicketRequest(ticket_id=ticket_id))
        assert t.ticket["status"] == "NEW"

        # Step 2: resolve queue
        q = OtrsService.resolve_mrf_queue(ResolveMrfQueueRequest(region="MSK"))
        assert q.queue

        # Step 3: update ticket
        OtrsService.update_ticket(UpdateOtrsTicketRequest(
            ticket_id=ticket_id, queue=q.queue, status=OtrsStatus.OPEN,
        ))

        # Step 4: add comment
        OtrsService.add_comment(AddOtrsCommentRequest(
            ticket_id=ticket_id, text="Processed by integration test"
        ))

        # Step 5: verify ticket state
        t2 = OtrsService.get_ticket(GetOtrsTicketRequest(ticket_id=ticket_id))
        assert t2.ticket["status"] == "OPEN"
        assert t2.ticket["queue"] == q.queue

        # Step 6: verify comment
        comments = OtrsService.list_comments(ListOtrsCommentsRequest(ticket_id=ticket_id))
        assert any("integration test" in c.get("text", "") for c in comments.comments)


class TestStorageIsolation:
    """Integration: verify that storage changes are isolated per test."""

    @pytest.mark.integration
    def test_modify_storage(self):
        storage.ORDERS_DB["TEMP_ORDER"] = {"status": "CREATED", "comment": "temp"}
        assert "TEMP_ORDER" in storage.ORDERS_DB

    @pytest.mark.integration
    def test_verify_clean_storage(self):
        assert "TEMP_ORDER" not in storage.ORDERS_DB


class TestMultiOrderOperations:
    """Integration: operations across multiple orders."""

    @pytest.mark.integration
    def test_batch_status_check(self):
        orders = ["1800003902272", "1800003879400"]
        results = {}
        for oid in orders:
            try:
                resp = OrderService.get_order_status(GetOrderStatusRequest(order_id=oid))
                results[oid] = resp.status.value
            except ValueError:
                results[oid] = "NOT_FOUND"

        assert results["1800003902272"] == "DENIED"
        assert results["1800003879400"] == "DENIED"

    @pytest.mark.integration
    def test_update_preserves_other_orders(self):
        OrderService.update_order_status(
            UpdateOrderStatusRequest(order_id="1800003902272", new_status=OrderStatus.DONE)
        )
        other = OrderService.get_order_status(GetOrderStatusRequest(order_id="1800003879400"))
        assert other.status == OrderStatus.DENIED
