"""Block E — Fault class definitions.

Defines the 6 realistic fault classes used in fault injection experiments:
1. LatencyFault — adds artificial delay
2. TimeoutFault — simulates request timeout
3. DependencyFailureFault — external dependency returns error
4. PartialUnavailableFault — service intermittently fails
5. ResourceDegradationFault — system resource pressure
6. NetworkDegradationFault — packet loss / corruption simulation

Each fault is a callable that wraps a service function and injects the
fault behaviour.
"""

from __future__ import annotations

import enum
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


class FaultClass(str, enum.Enum):
    LATENCY = "latency"
    TIMEOUT = "timeout"
    DEPENDENCY_FAILURE = "dependency_failure"
    PARTIAL_UNAVAILABLE = "partial_unavailable"
    RESOURCE_DEGRADATION = "resource_degradation"
    NETWORK_DEGRADATION = "network_degradation"


@dataclass
class FaultSpec:
    """Specification for a single fault injection."""
    fault_class: FaultClass
    target_call: str = ""               # which service call to inject into ("" = all)
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    injected_at: Optional[float] = None # timestamp when fault was activated

    def activate(self) -> None:
        self.enabled = True
        self.injected_at = time.time()

    def deactivate(self) -> None:
        self.enabled = False


# ---------------------------------------------------------------------------
# Fault implementations
# ---------------------------------------------------------------------------

class LatencyFault:
    """Injects artificial latency (delay_ms) before executing the call."""

    def __init__(self, delay_ms: float = 500.0):
        self.delay_ms = delay_ms

    def __call__(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        time.sleep(self.delay_ms / 1000.0)
        return func(*args, **kwargs)


class TimeoutFault:
    """Simulates a timeout by sleeping then raising TimeoutError."""

    def __init__(self, delay_ms: float = 5000.0):
        self.delay_ms = delay_ms

    def __call__(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        time.sleep(self.delay_ms / 1000.0)
        raise TimeoutError(f"Simulated timeout after {self.delay_ms}ms")


class DependencyFailureFault:
    """Simulates dependency failure with a configurable error."""

    def __init__(self, error_message: str = "Dependency unavailable", error_cls: type = ConnectionError):
        self.error_message = error_message
        self.error_cls = error_cls

    def __call__(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        raise self.error_cls(self.error_message)


class PartialUnavailableFault:
    """Fails intermittently with a given failure_rate (0.0 – 1.0)."""

    def __init__(self, failure_rate: float = 0.5):
        self.failure_rate = max(0.0, min(1.0, failure_rate))

    def __call__(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        if random.random() < self.failure_rate:
            raise ConnectionError("Service partially unavailable")
        return func(*args, **kwargs)


class ResourceDegradationFault:
    """Simulates resource pressure by consuming CPU time."""

    def __init__(self, cpu_burn_ms: float = 200.0):
        self.cpu_burn_ms = cpu_burn_ms

    def __call__(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        deadline = time.perf_counter() + (self.cpu_burn_ms / 1000.0)
        while time.perf_counter() < deadline:
            _ = sum(range(1000))
        return func(*args, **kwargs)


class NetworkDegradationFault:
    """Simulates network issues: random delay + optional corruption."""

    def __init__(
        self,
        jitter_ms: float = 100.0,
        corruption_rate: float = 0.0,
    ):
        self.jitter_ms = jitter_ms
        self.corruption_rate = max(0.0, min(1.0, corruption_rate))

    def __call__(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        delay = random.uniform(0, self.jitter_ms) / 1000.0
        time.sleep(delay)

        result = func(*args, **kwargs)

        if random.random() < self.corruption_rate:
            raise IOError("Network corruption: malformed response")

        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

FAULT_REGISTRY: Dict[FaultClass, type] = {
    FaultClass.LATENCY: LatencyFault,
    FaultClass.TIMEOUT: TimeoutFault,
    FaultClass.DEPENDENCY_FAILURE: DependencyFailureFault,
    FaultClass.PARTIAL_UNAVAILABLE: PartialUnavailableFault,
    FaultClass.RESOURCE_DEGRADATION: ResourceDegradationFault,
    FaultClass.NETWORK_DEGRADATION: NetworkDegradationFault,
}


def create_fault(spec: FaultSpec) -> Callable:
    """Create a fault implementation from a FaultSpec."""
    cls = FAULT_REGISTRY.get(spec.fault_class)
    if cls is None:
        raise ValueError(f"Unknown fault class: {spec.fault_class}")
    return cls(**spec.params)
