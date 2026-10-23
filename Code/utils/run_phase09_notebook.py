"""
Execute Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb end-to-end with the interpreter running this script:
    C:\\Python313\\python.exe Code/utils/run_phase09_notebook.py
Thin wrapper around Code/utils/run_notebook.py (see there for why the interpreter is pinned).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_notebook import run  # noqa: E402

sys.exit(run(Path("Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb")))
