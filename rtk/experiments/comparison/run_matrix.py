"""Alias entrypoint: ``python -m experiments.comparison.run_matrix``.

Delegates to the main experiment orchestrator.
"""

from experiments.__main__ import cli

if __name__ == "__main__":
    cli()
