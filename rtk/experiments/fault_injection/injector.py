"""Block E — Fault injection mechanism.

Provides a FaultInjector that wraps service calls and selectively
applies fault behaviour based on active FaultSpecs.

Key features:
- Controlled injection (enable/disable per fault)
- Target-specific injection (by call name)
- Recording of injection events for later analysis
- Repeatable: same seed → same random faults
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .faults import FaultClass, FaultSpec, create_fault


@dataclass
class InjectionEvent:
    """Record of a single fault injection."""
    timestamp: float = field(default_factory=time.time)
    fault_class: FaultClass = FaultClass.LATENCY
    target_call: str = ""
    success: bool = True
    error: Optional[str] = None


class FaultInjector:
    """Manages fault specs and wraps service calls with fault injection.

    Usage::

        injector = FaultInjector()
        injector.add_fault(FaultSpec(
            fault_class=FaultClass.LATENCY,
            target_call="get_order_status",
            params={"delay_ms": 500},
        ))

        # Wrap a service call
        result = injector.call(get_order_status, args, call_name="get_order_status")
    """

    def __init__(self) -> None:
        self._faults: List[FaultSpec] = []
        self._events: List[InjectionEvent] = []
        self._implementations: Dict[int, Callable] = {}

    @property
    def events(self) -> List[InjectionEvent]:
        return list(self._events)

    @property
    def fault_specs(self) -> List[FaultSpec]:
        return list(self._faults)

    def add_fault(self, spec: FaultSpec) -> None:
        """Register a fault spec. Creates the implementation eagerly."""
        spec.activate()
        self._faults.append(spec)
        self._implementations[id(spec)] = create_fault(spec)

    def remove_all(self) -> None:
        """Remove all fault specs."""
        for s in self._faults:
            s.deactivate()
        self._faults.clear()
        self._implementations.clear()

    def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        call_name: str = "",
        **kwargs: Any,
    ) -> Any:
        """Execute func, injecting faults that match call_name."""
        call_name = call_name or getattr(func, "__name__", "unknown")

        # Find matching active faults
        for spec in self._faults:
            if not spec.enabled:
                continue
            if spec.target_call and spec.target_call != call_name:
                continue

            impl = self._implementations.get(id(spec))
            if impl is None:
                continue

            event = InjectionEvent(
                fault_class=spec.fault_class,
                target_call=call_name,
            )
            try:
                result = impl(func, *args, **kwargs)
                event.success = True
                self._events.append(event)
                return result
            except Exception as exc:
                event.success = False
                event.error = str(exc)
                self._events.append(event)
                raise

        # No fault matched → execute normally
        return func(*args, **kwargs)

    def create_wrapped_dispatcher(
        self,
        base_dispatcher: Callable[[str, Dict[str, Any]], Any],
    ) -> Callable[[str, Dict[str, Any]], Any]:
        """Create a dispatcher that injects faults before delegating."""
        def wrapped(call_name: str, arguments: Dict[str, Any]) -> Any:
            return self.call(
                base_dispatcher,
                call_name,
                arguments,
                call_name=call_name,
            )
        return wrapped
