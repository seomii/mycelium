# Mycelium UV analysis package

This package contains a reproducible analysis of the uploaded mycelium UV
recordings.

## Files

- `mycelium_analysis.py` — the complete Python analysis.
- `mycelium_analysis.ipynb` — an interactive notebook version of the same analysis, organized step-by-step.
- `mycelium_results.tex` — LaTeX report.
- `data/` — raw `.npy` recordings used in the analysis.
- `figures/` — publication-quality PNG figures.
- `results/` — cycle-level CSV data and generated LaTeX summary table.

## Reproduce

Install the Python dependencies:

    numpy
    pandas
    matplotlib
    scipy

For an interactive walkthrough, open `mycelium_analysis.ipynb` in Jupyter or VS Code and run the cells in order.

Then run:

    python mycelium_analysis.py

After that, compile:

    pdflatex mycelium_results.tex
    pdflatex mycelium_results.tex

The second LaTeX pass resolves references.

## Important interpretation

There is one unloaded recording and two loaded recordings with the same
nominal static weight. The 30 UV cycles are repeated measurements within an
experiment, not independent biological replicates. The current results are
therefore exploratory/pilot observations and should not be used to claim a
statistically established causal effect of static loading.
