"""Unified experiment entrypoint.

Usage::

    # Full matrix run (default)
    python -m experiments

    # Run with custom repeat count
    python -m experiments --repeats 5

    # Skip visualization export
    python -m experiments --no-figures

This module orchestrates:

1. Matrix experiment run (A0/A1/A2/A3 × scenarios × obs_levels × repeats)
2. Aggregation and dataset export (raw_runs.jsonl + aggregated.csv)
3. Diploma tables and summaries (CSV, JSON, Markdown)
4. Static scientific figures (PNG/SVG)
5. Case-study artifacts (JSON)

Equivalent to ``python -m experiments.comparison.run_matrix``.
"""

from __future__ import annotations

import argparse
import sys

from experiments.run_experiments import main as run_matrix, N_REPEATS, OUTPUT_DIR


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full experiment matrix and generate artifacts.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=N_REPEATS,
        help=f"Number of repetitions per scenario (default: {N_REPEATS})",
    )
    parser.add_argument(
        "--no-figures",
        action="store_true",
        help="Skip figure export (faster for CI runs)",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_DIR,
        help=f"Output directory (default: {OUTPUT_DIR})",
    )
    args = parser.parse_args()

    # Patch repeat count if overridden
    import experiments.run_experiments as _mod
    _mod.N_REPEATS = args.repeats
    _mod.OUTPUT_DIR = args.output

    # Step 1: run matrix experiments
    print("=" * 72)
    print("  STEP 1/4: Running experiment matrix")
    print("=" * 72)
    run_matrix()

    # Step 2: generate tables and summaries
    print("\n" + "=" * 72)
    print("  STEP 2/4: Generating diploma tables & summaries")
    print("=" * 72)
    _generate_tables_and_summaries(args.output, args.repeats)

    # Step 3: case studies
    print("\n" + "=" * 72)
    print("  STEP 3/4: Building case-study artifacts")
    print("=" * 72)
    _build_case_studies(args.output)

    # Step 4: figures (optional)
    if not args.no_figures:
        print("\n" + "=" * 72)
        print("  STEP 4/4: Exporting scientific figures")
        print("=" * 72)
        _export_figures(args.output)
    else:
        print("\n  [skipped] Figure export (--no-figures)")

    print("\n" + "=" * 72)
    print("  ALL DONE")
    print("=" * 72)


def _generate_tables_and_summaries(output_dir: str, n_repeats: int) -> None:
    import os
    from experiments.dataset.writer import DatasetWriter
    from experiments.sciexport import (
        export_diploma_tables,
        export_summary_json,
        export_summary_markdown,
        gather_reproducibility_metadata,
    )

    writer = DatasetWriter(output_dir=output_dir)
    records = writer.load_raw_runs()
    if not records:
        print("  No raw records found — skipping.")
        return

    tables_dir = os.path.join(output_dir, "tables")
    summary_dir = os.path.join(output_dir, "summary")

    written = export_diploma_tables(records, output_dir=tables_dir)
    print(f"  Wrote {len(written)} table files → {tables_dir}")

    path = export_summary_json(records, output_dir=summary_dir, n_repeats=n_repeats)
    print(f"  Wrote summary JSON → {path}")

    path = export_summary_markdown(records, output_dir=summary_dir)
    print(f"  Wrote summary Markdown → {path}")

    # Reproducibility metadata
    import json
    meta = gather_reproducibility_metadata(results_dir=output_dir, n_repeats=n_repeats)
    meta_path = os.path.join(summary_dir, "reproducibility.json")
    os.makedirs(summary_dir, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"  Wrote reproducibility metadata → {meta_path}")


def _build_case_studies(output_dir: str) -> None:
    import os
    from experiments.dataset.writer import DatasetWriter
    from experiments.casestudy.builder import build_and_save_case_studies

    writer = DatasetWriter(output_dir=output_dir)
    records = writer.load_raw_runs()
    if not records:
        print("  No raw records found — skipping.")
        return

    cs_dir = os.path.join(output_dir, "casestudies")
    paths = build_and_save_case_studies(records, output_dir=cs_dir)
    for p in paths:
        print(f"  Wrote case study → {p}")
    if not paths:
        print("  No matching scenarios for case studies.")


def _export_figures(output_dir: str) -> None:
    import os
    from experiments.sciexport import export_diploma_figures

    fig_dir = os.path.join(output_dir, "figures")
    paths = export_diploma_figures(
        results_dir=output_dir,
        output_dir=fig_dir,
        formats=("png",),
    )
    print(f"  Exported {len(paths)} figures → {fig_dir}")


if __name__ == "__main__":
    cli()
