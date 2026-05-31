"""In-process mock MCP client for the LLM experiment.

Wraps service_dispatcher so that tool calls run in-process without
needing a real MCP stdio connection.  This lets the experiment be
fully self-contained and deterministic.
"""

from __future__ import annotations

from typing import Any, Dict, List

from experiments.shared import service_dispatcher


# Minimal OpenAI-compatible tool schema presented to the mock LLM providers.
# Covers the tools relevant to order-status diagnosis.
TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": "Search order logs for a specific error code pattern",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "pattern": {"type": "string"},
                },
                "required": ["order_id", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Get current order status from SULZ DB",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_eissd_status",
            "description": "Check order status in external EISSD system",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_otrs_comments",
            "description": "List comments attached to an OTRS ticket",
            "parameters": {
                "type": "object",
                "properties": {"ticket_id": {"type": "string"}},
                "required": ["ticket_id"],
            },
        },
    },
]


class MockMCPClient:
    """Synchronous-backed async MCP client using service_dispatcher.

    Raises ValueError for any tool not registered in service_dispatcher,
    which mirrors the behaviour of a real MCP server receiving an unknown
    tool name.
    """

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        return TOOLS_SCHEMA

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        # service_dispatcher raises ValueError("Unknown call: X") for unknown tools
        return service_dispatcher(name, arguments)
