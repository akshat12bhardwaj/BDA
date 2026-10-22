"""
Execute Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb end-to-end with the SAME interpreter that runs this
script (e.g. `C:\\Python313\\python.exe Code/utils/run_phase09_notebook.py` from the project root).

Why: the machine has two Pythons; the default `python3` kernelspec can resolve to Anaconda 3.12 (scikit-learn 1.5)
instead of the project's 3.13 (scikit-learn 1.8). This writes a temporary `python3` kernelspec pointing at
sys.executable and puts it first on JUPYTER_PATH for this run only - nothing is installed or reconfigured.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

NOTEBOOK = Path("Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb")

with tempfile.TemporaryDirectory() as tmp:
    spec = Path(tmp) / "kernels" / "python3"
    spec.mkdir(parents=True)
    (spec / "kernel.json").write_text(json.dumps({
        "argv": [Path(sys.executable).as_posix(), "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": f"Python 3 ({sys.executable})", "language": "python"}), encoding="utf-8")
    env = os.environ | {"JUPYTER_PATH": tmp, "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
                    "--ExecutePreprocessor.timeout=3600", "--ExecutePreprocessor.kernel_name=python3", str(NOTEBOOK)],
                   env=env, check=True)

nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
errors = sum(o.get("output_type") == "error" for c in nb["cells"] for o in c.get("outputs", []))
print(f"executed with Python {nb['metadata']['language_info']['version']}; error outputs: {errors}")
sys.exit(1 if errors else 0)
