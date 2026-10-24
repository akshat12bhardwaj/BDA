"""
Contract tests for the read-only teaching notebooks (Phase 8 walkthrough and the project demonstration):
executed with Python 3.13 and without errors, no absolute paths, no re-running or writing of frozen work,
raw feature reads limited to the validation cutoff, and working links to the other notebooks.
"""

import json
import re
from pathlib import Path

import pytest

NB_DIR = Path("Notebooks")
READ_ONLY = ["Phase_08_Price_Forecasting.ipynb", "Overview_00_Project_Demonstration.ipynb"]
FORBIDDEN = ["run_build(", "run_models(", "run_test_evaluation(", "run_baselines(", "run_uncertainty(", "run_selection(",
             "run_error_profile(", "run_aq1(", "run_arrivals_baselines(", "run_audit(", "fit_predict(", "freeze(",
             ".to_csv(", ".to_parquet(", "write_config(", "run_test(", "preflight("]


def load(name):
    return json.loads((NB_DIR / name).read_text(encoding="utf-8"))


def code_cells(nb):
    return [c for c in nb["cells"] if c["cell_type"] == "code"]


@pytest.mark.parametrize("name", READ_ONLY + ["Phase_09_Arrivals_Model_Experiments.ipynb"])
def test_notebook_executed_with_project_python_and_no_errors(name):
    nb = load(name)
    assert nb["metadata"]["kernelspec"]["name"] == "python3"
    assert nb["metadata"]["language_info"]["version"].startswith("3.13")
    cells = code_cells(nb)
    assert cells and all(c.get("execution_count") for c in cells)
    assert not any(o.get("output_type") == "error" for c in cells for o in c.get("outputs", []))
    src = "\n".join("".join(c["source"]) for c in cells)
    assert "C:/" not in src.replace("C:\\\\Python313", "") and "PROJECT_ROOT" in src


@pytest.mark.parametrize("name", READ_ONLY)
def test_read_only_notebooks_never_rerun_fit_or_write(name):
    src = "\n".join("".join(c["source"]) for c in code_cells(load(name)))
    assert not [f for f in FORBIDDEN if f in src.replace("verify_freeze(", "")]


@pytest.mark.parametrize("name", READ_ONLY)
def test_raw_feature_reads_stop_at_the_validation_cutoff(name):
    for c in code_cells(load(name)):
        s = "".join(c["source"])
        if "FEATURE_DIR" in s and "read_parquet" in s:
            assert "CUTOFF" in s, s[:200]


@pytest.mark.parametrize("name", READ_ONLY)
def test_notebook_links_resolve(name):
    text = "\n".join("".join(c["source"]) for c in load(name)["cells"] if c["cell_type"] == "markdown")
    links = re.findall(r"\]\(([^)]+\.ipynb)\)", text)
    assert all((NB_DIR / link).exists() for link in links)


def test_demo_points_to_both_phase_notebooks():
    text = "\n".join("".join(c["source"]) for c in load("Overview_00_Project_Demonstration.ipynb")["cells"])
    assert "Phase_08_Price_Forecasting.ipynb" in text and "Phase_09_Arrivals_Model_Experiments.ipynb" in text
