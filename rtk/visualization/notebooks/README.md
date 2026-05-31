# Visualization — Jupyter Notebooks

This directory is reserved for analysis notebooks.

Recommended workflow:

```bash
cd visualization/notebooks
jupyter lab
```

Create notebooks that import from the analysis and visualization modules:

```python
from experiments.analysis.statistics import load_raw_runs, generate_diploma_tables
from experiments.visualization.plots import plot_comparative_view
from experiments.visualization.export import export_figure
```
