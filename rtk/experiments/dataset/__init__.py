"""Dataset I/O — re-exports from :mod:`writer`."""

from __future__ import annotations

from .writer import DatasetWriter, aggregate_runs

__all__ = [
    "DatasetWriter",
    "aggregate_runs",
]
