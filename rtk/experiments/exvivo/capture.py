"""Block D — Runtime interaction capture.

Records API / inter-service interactions during test scenarios so they can
be normalised and replayed later as regression tests.

Each captured interaction is a CapturedInteraction dataclass that stores:
- service call details (tool name, arguments, response)
- timing information
- trace / request context
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class CapturedInteraction:
    """A single recorded service interaction."""
    interaction_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    call_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    response: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    elapsed_ms: float = 0.0
    trace_id: Optional[str] = None
    request_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapturedScenario:
    """A sequence of interactions that form one user scenario."""
    scenario_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    interactions: List[CapturedInteraction] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class InteractionCapture:
    """Captures interactions during test / scenario execution.

    Usage::

        cap = InteractionCapture()
        cap.start_scenario("my_scenario")
        # ... execute system calls via cap.record(...) ...
        scenario = cap.finish_scenario()
    """

    def __init__(self) -> None:
        self._scenarios: List[CapturedScenario] = []
        self._current: Optional[CapturedScenario] = None
        self._trace_id: Optional[str] = None

    @property
    def scenarios(self) -> List[CapturedScenario]:
        return list(self._scenarios)

    def start_scenario(self, name: str = "", metadata: Optional[Dict[str, Any]] = None) -> str:
        tid = uuid.uuid4().hex[:16]
        self._trace_id = tid
        self._current = CapturedScenario(
            name=name,
            metadata=metadata or {},
        )
        return tid

    def record(
        self,
        call_name: str,
        arguments: Dict[str, Any],
        response: Any = None,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
        elapsed_ms: float = 0.0,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> CapturedInteraction:
        interaction = CapturedInteraction(
            call_name=call_name,
            arguments=copy.deepcopy(arguments),
            response=copy.deepcopy(response),
            error=error,
            error_type=error_type,
            elapsed_ms=elapsed_ms,
            trace_id=self._trace_id,
            request_context=request_context or {},
        )
        if self._current is not None:
            self._current.interactions.append(interaction)
        return interaction

    def record_call(
        self,
        func: Callable[..., Any],
        *args: Any,
        call_name: str = "",
        arguments_dict: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Execute func, record the interaction, return the result."""
        call_name = call_name or getattr(func, "__name__", "unknown")
        args_dict = arguments_dict or {"args": args, "kwargs": kwargs}
        t0 = time.perf_counter()
        error_str = None
        error_type = None
        result = None
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as exc:
            error_str = str(exc)
            error_type = type(exc).__name__
            raise
        finally:
            elapsed = (time.perf_counter() - t0) * 1000.0
            self.record(
                call_name=call_name,
                arguments=args_dict,
                response=result,
                error=error_str,
                error_type=error_type,
                elapsed_ms=elapsed,
            )

    def finish_scenario(self) -> Optional[CapturedScenario]:
        if self._current is None:
            return None
        self._current.finished_at = time.time()
        scenario = self._current
        self._scenarios.append(scenario)
        self._current = None
        self._trace_id = None
        return scenario

    def export_json(self) -> str:
        """Serialise all captured scenarios to JSON."""
        data = []
        for sc in self._scenarios:
            data.append({
                "scenario_id": sc.scenario_id,
                "name": sc.name,
                "started_at": sc.started_at,
                "finished_at": sc.finished_at,
                "metadata": sc.metadata,
                "interactions": [
                    {
                        "interaction_id": i.interaction_id,
                        "timestamp": i.timestamp,
                        "call_name": i.call_name,
                        "arguments": i.arguments,
                        "response": _safe_serialize(i.response),
                        "error": i.error,
                        "error_type": i.error_type,
                        "elapsed_ms": i.elapsed_ms,
                        "trace_id": i.trace_id,
                    }
                    for i in sc.interactions
                ],
            })
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def import_json(raw: str) -> List[CapturedScenario]:
        """Deserialise scenarios from JSON."""
        items = json.loads(raw)
        scenarios = []
        for item in items:
            interactions = []
            for ix in item.get("interactions", []):
                interactions.append(CapturedInteraction(
                    interaction_id=ix.get("interaction_id", ""),
                    timestamp=ix.get("timestamp", 0),
                    call_name=ix.get("call_name", ""),
                    arguments=ix.get("arguments", {}),
                    response=ix.get("response"),
                    error=ix.get("error"),
                    error_type=ix.get("error_type"),
                    elapsed_ms=ix.get("elapsed_ms", 0),
                    trace_id=ix.get("trace_id"),
                ))
            scenarios.append(CapturedScenario(
                scenario_id=item.get("scenario_id", ""),
                name=item.get("name", ""),
                interactions=interactions,
                started_at=item.get("started_at", 0),
                finished_at=item.get("finished_at"),
                metadata=item.get("metadata", {}),
            ))
        return scenarios


def _safe_serialize(obj: Any) -> Any:
    """Best-effort JSON-safe representation."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}
    return str(obj)
