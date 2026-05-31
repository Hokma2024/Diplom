"""Visualization — dashboard sub-package.

Re-exports the Dash application from the experiment dashboard module.
"""

from experiments.dashboard.app import app, run_dashboard

__all__ = ["app", "run_dashboard"]
