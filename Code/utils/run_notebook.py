"""
Execute a project notebook end-to-end with the SAME interpreter that runs this script, from the project root:
    C:\\Python313\\python.exe Code/utils/run_notebook.py Notebooks/<name>.ipynb

Why: this machine has two Pythons. A plain `jupyter ...` command resolves to Anaconda's launcher (JupyterLab 4.2.5,
Python 3.12 kernel, scikit-learn 1.5). Here nbconvert runs as a module of sys.executable, and a temporary `python3`
kernelspec pointing at sys.executable is put first on JUPYTER_PATH for this run only. Nothing is installed or
reconfigured.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(notebook: Path) -> int:
    notebook = Path(notebook)
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "kernels" / "python3"
        spec.mkdir(parents=True)
        (spec / "kernel.json").write_text(json.dumps({
            "argv": [Path(sys.executable).as_posix(), "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": f"Python 3 ({sys.executable})", "language": "python"}), encoding="utf-8")
        env = os.environ | {"JUPYTER_PATH": tmp, "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run([sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace",
                        "--ExecutePreprocessor.timeout=3600", "--ExecutePreprocessor.kernel_name=python3", str(notebook)],
                       env=env, check=True)
    nb = json.loads(notebook.read_text(encoding="utf-8"))
    errors = sum(o.get("output_type") == "error" for c in nb["cells"] for o in c.get("outputs", []))
    print(f"{notebook.name}: executed with Python {nb['metadata']['language_info']['version']}; error outputs: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python Code/utils/run_notebook.py Notebooks/<name>.ipynb")
    sys.exit(run(Path(sys.argv[1])))
