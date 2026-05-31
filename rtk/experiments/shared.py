"""Shared utilities for experiment runners.

Contains the service dispatcher and fault-parameter defaults used by both
run_experiments.py and comparison/runner.py to avoid duplication.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.mcp_server.models import (
    AddOtrsCommentRequest,
    CheckEissdStatusRequest,
    GetOrderStatusRequest,
    GetOtrsTicketRequest,
    ListOtrsCommentsRequest,
    SearchLogsRequest,
)
from services.mcp_server.services import OrderService, OtrsService
from experiments.fault_injection.faults import FaultClass


# Maps scenario fault_class strings to FaultClass enum values.
# None means "no injection" (used for signal_loss / sparsity scenarios).
FAULT_CLASS_MAP: Dict[str, Optional[FaultClass]] = {
    "latency": FaultClass.LATENCY,
    "timeout": FaultClass.TIMEOUT,
    "dependency_down": FaultClass.DEPENDENCY_FAILURE,
    "dependency_failure": FaultClass.DEPENDENCY_FAILURE,
    "partial_outage": FaultClass.PARTIAL_UNAVAILABLE,
    "partial_unavailable": FaultClass.PARTIAL_UNAVAILABLE,
    "resource_pressure": FaultClass.RESOURCE_DEGRADATION,
    "resource_degradation": FaultClass.RESOURCE_DEGRADATION,
    "network_fault": FaultClass.NETWORK_DEGRADATION,
    "network_degradation": FaultClass.NETWORK_DEGRADATION,
    # Correlation-break is modelled as latency (observable delay)
    "correlation_break": FaultClass.LATENCY,
    # Signal-loss: no fault injected — tests that sparse signals → no detection
    "signal_loss": None,
}


def service_dispatcher(call_name: str, arguments: Dict[str, Any]) -> Any:
    """Route call_name to the appropriate MCP service method."""
    dispatch: Dict[str, Any] = {
        "search_logs": lambda a: OrderService.search_logs(
            SearchLogsRequest(**a)
        ).model_dump(),
        "get_order_status": lambda a: OrderService.get_order_status(
            GetOrderStatusRequest(**a)
        ).model_dump(),
        "check_eissd_status": lambda a: OrderService.check_eissd_status(
            CheckEissdStatusRequest(**a)
        ).model_dump(),
        "add_otrs_comment": lambda a: OtrsService.add_comment(
            AddOtrsCommentRequest(**a)
        ).model_dump(),
        "list_otrs_comments": lambda a: OtrsService.list_comments(
            ListOtrsCommentsRequest(**a)
        ).model_dump(),
        "get_otrs_ticket": lambda a: OtrsService.get_ticket(
            GetOtrsTicketRequest(**a)
        ).model_dump(),
    }
    if call_name in dispatch:
        return dispatch[call_name](arguments)
    raise ValueError(f"Unknown call: {call_name}")


def fault_params_for(fc: FaultClass) -> Dict[str, Any]:
    """Return default fault parameters for a given FaultClass.

    Timeout uses 200 ms (not 5 s) so the experiment matrix stays fast;
    it still raises TimeoutError, which is all that matters for detection.
    """
    defaults: Dict[FaultClass, Dict[str, Any]] = {
        FaultClass.LATENCY: {"delay_ms": 200},
        FaultClass.TIMEOUT: {"delay_ms": 200},
        FaultClass.DEPENDENCY_FAILURE: {"error_message": "Injected dependency failure"},
        FaultClass.PARTIAL_UNAVAILABLE: {"failure_rate": 0.5},
        FaultClass.RESOURCE_DEGRADATION: {"cpu_burn_ms": 50},
        FaultClass.NETWORK_DEGRADATION: {"jitter_ms": 100},
    }
    return defaults.get(fc, {})
