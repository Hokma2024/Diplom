"""Block D — Ex-vivo regression tests.

Captures interactions from the test system, normalises them, then replays
to verify that the system behaviour hasn't regressed.

These tests demonstrate the ex-vivo pipeline:
1. Capture interactions during a known-good scenario
2. Normalise captured data (strip timestamps, IDs)
3. Replay against the same system
4. Detect regressions by comparing responses
"""

from __future__ import annotations

import copy
import json
import pytest
from typing import Any, Dict

from services.mcp_server.models import (
    SearchLogsRequest,
    GetOrderStatusRequest,
    CheckEissdStatusRequest,
    UpdateOrderStatusRequest,
    AddOtrsCommentRequest,
    ListOtrsCommentsRequest,
    GetOtrsTicketRequest,
    UpdateOtrsTicketRequest,
    OrderStatus,
    OtrsStatus,
)
from services.mcp_server.services import OrderService, OtrsService
from services.mcp_server import storage

from experiments.exvivo.capture import InteractionCapture, CapturedScenario
from experiments.exvivo.normalize import InteractionNormaliser, NormalisationConfig
from experiments.exvivo.replay import ReplayEngine, ScenarioReplayResult


# ---------------------------------------------------------------------------
# Service dispatcher for replay
# ---------------------------------------------------------------------------

_DISPATCH_MAP = {
    "search_logs": lambda args: OrderService.search_logs(SearchLogsRequest(**args)).model_dump(),
    "get_order_status": lambda args: OrderService.get_order_status(GetOrderStatusRequest(**args)).model_dump(),
    "check_eissd_status": lambda args: OrderService.check_eissd_status(CheckEissdStatusRequest(**args)).model_dump(),
    "resolve_mrf_queue": lambda args: OtrsService.resolve_mrf_queue(
        from_import("services.mcp_server.models", "ResolveMrfQueueRequest")(**args)
    ).model_dump(),
    "add_otrs_comment": lambda args: OtrsService.add_comment(AddOtrsCommentRequest(**args)).model_dump(),
    "list_otrs_comments": lambda args: OtrsService.list_comments(ListOtrsCommentsRequest(**args)).model_dump(),
    "get_otrs_ticket": lambda args: OtrsService.get_ticket(GetOtrsTicketRequest(**args)).model_dump(),
}


def from_import(module: str, name: str):
    import importlib
    mod = importlib.import_module(module)
    return getattr(mod, name)


def service_dispatcher(call_name: str, arguments: Dict[str, Any]) -> Any:
    if call_name in _DISPATCH_MAP:
        return _DISPATCH_MAP[call_name](arguments)
    raise ValueError(f"Unknown call: {call_name}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExVivoCaptureAndReplay:
    """Capture → normalise → replay → verify no regressions."""

    @pytest.mark.exvivo
    def test_capture_search_logs(self):
        """Capture search_logs interaction and verify capture correctness."""
        cap = InteractionCapture()
        cap.start_scenario("search_denied_logs")

        result = cap.record_call(
            lambda: OrderService.search_logs(
                SearchLogsRequest(order_id="1800003902272", pattern="ORDER_STATUS_DENIED")
            ).model_dump(),
            call_name="search_logs",
            arguments_dict={"order_id": "1800003902272", "pattern": "ORDER_STATUS_DENIED"},
        )

        scenario = cap.finish_scenario()
        assert scenario is not None
        assert len(scenario.interactions) == 1
        assert scenario.interactions[0].call_name == "search_logs"
        assert result["error_found"] is True

    @pytest.mark.exvivo
    def test_full_capture_normalise_replay_cycle(self):
        """Full ex-vivo cycle: capture → normalise → serialise → replay."""
        # 1. Capture
        cap = InteractionCapture()
        cap.start_scenario("denied_order_investigation")

        cap.record_call(
            lambda: OrderService.search_logs(
                SearchLogsRequest(order_id="1800003902272", pattern="ORDER_STATUS_DENIED")
            ).model_dump(),
            call_name="search_logs",
            arguments_dict={"order_id": "1800003902272", "pattern": "ORDER_STATUS_DENIED"},
        )
        cap.record_call(
            lambda: OrderService.get_order_status(
                GetOrderStatusRequest(order_id="1800003902272")
            ).model_dump(),
            call_name="get_order_status",
            arguments_dict={"order_id": "1800003902272"},
        )
        cap.record_call(
            lambda: OrderService.check_eissd_status(
                CheckEissdStatusRequest(order_id="1800003902272")
            ).model_dump(),
            call_name="check_eissd_status",
            arguments_dict={"order_id": "1800003902272"},
        )

        scenario = cap.finish_scenario()
        assert len(scenario.interactions) == 3

        # 2. Normalise
        normaliser = InteractionNormaliser()
        normalised = normaliser.normalise_scenario(scenario)
        assert normalised.started_at == 0.0
        assert all(ix.timestamp == 0.0 for ix in normalised.interactions)

        # 3. Serialise / Deserialise round-trip
        json_str = cap.export_json()
        imported = InteractionCapture.import_json(json_str)
        assert len(imported) == 1
        assert len(imported[0].interactions) == 3

        # 4. Replay
        engine = ReplayEngine(dispatcher=service_dispatcher)
        result = engine.replay_scenario(scenario)

        assert result.total_interactions == 3
        assert result.matched == 3
        assert result.mismatched == 0
        assert result.has_regressions is False
        assert result.match_rate == 1.0

    @pytest.mark.exvivo
    def test_replay_detects_regression(self):
        """Introduce a change and verify replay detects it."""
        # 1. Capture baseline
        cap = InteractionCapture()
        cap.start_scenario("baseline_status_check")

        cap.record_call(
            lambda: OrderService.get_order_status(
                GetOrderStatusRequest(order_id="1800003902272")
            ).model_dump(),
            call_name="get_order_status",
            arguments_dict={"order_id": "1800003902272"},
        )
        scenario = cap.finish_scenario()

        # 2. Modify storage (simulate regression)
        storage.ORDERS_DB["1800003902272"]["status"] = "DONE"

        # 3. Replay
        engine = ReplayEngine(dispatcher=service_dispatcher)
        result = engine.replay_scenario(scenario)

        assert result.has_regressions is True
        assert result.mismatched >= 1

    @pytest.mark.exvivo
    def test_replay_with_error_scenario(self):
        """Capture an error interaction and replay it."""
        cap = InteractionCapture()
        cap.start_scenario("missing_order")

        try:
            cap.record_call(
                lambda: OrderService.get_order_status(
                    GetOrderStatusRequest(order_id="NONEXISTENT")
                ).model_dump(),
                call_name="get_order_status",
                arguments_dict={"order_id": "NONEXISTENT"},
            )
        except ValueError:
            pass

        scenario = cap.finish_scenario()
        assert len(scenario.interactions) == 1
        assert scenario.interactions[0].error is not None

        # Replay should also get the error
        engine = ReplayEngine(dispatcher=service_dispatcher)
        result = engine.replay_scenario(scenario)
        assert result.matched == 1
        assert result.has_regressions is False


class TestNormalisation:
    """Test normalisation produces stable output."""

    @pytest.mark.exvivo
    def test_timestamps_zeroed(self):
        from experiments.exvivo.capture import CapturedInteraction
        ix = CapturedInteraction(
            call_name="test", arguments={"a": 1},
            response={"b": 2}, elapsed_ms=42.5,
        )
        scenario = CapturedScenario(name="test", interactions=[ix])
        normaliser = InteractionNormaliser()
        norm = normaliser.normalise_scenario(scenario)
        assert norm.started_at == 0.0
        assert norm.interactions[0].elapsed_ms == 0.0

    @pytest.mark.exvivo
    def test_ids_deterministic(self):
        normaliser = InteractionNormaliser()
        id1 = normaliser._norm_id("abc123def456")
        id2 = normaliser._norm_id("abc123def456")
        id3 = normaliser._norm_id("xyz789")
        assert id1 == id2
        assert id1 != id3

    @pytest.mark.exvivo
    def test_json_serialisation_roundtrip(self):
        cap = InteractionCapture()
        cap.start_scenario("roundtrip")
        cap.record("test_call", {"arg": "val"}, response={"result": True})
        cap.finish_scenario()

        json_str = cap.export_json()
        imported = InteractionCapture.import_json(json_str)
        assert len(imported) == 1
        assert imported[0].interactions[0].call_name == "test_call"
