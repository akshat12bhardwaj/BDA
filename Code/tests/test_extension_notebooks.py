"""
Contract tests for the read-only extension notebooks (candidate data, candidate experiments, the D-52 result and the
project guide): executed cleanly with Python 3.13, no absolute paths, no parquet or network reads, no fitting, running or
writing, no secrets in sources or outputs, and working notebook links.
"""

import json
import re
from pathlib import Path

import pytest

from Code.tests.test_notebooks import FORBIDDEN

NB_DIR = Path("Notebooks")
EXTENSIONS = sorted(p.name for p in NB_DIR.glob("Research_Extension_0*.ipynb"))
NO_READS = ["read_parquet", "requests", "urllib", "load_key", "api.data.gov.in/resource/", "import Code", "from Code",
            ".fit(", "run(", ".write_", "open("]


def load(name):
    return json.loads((NB_DIR / name).read_text(encoding="utf-8"))


def test_four_extension_notebooks_exist():
    assert EXTENSIONS == ["Research_Extension_01_Candidate_Price_Data.ipynb", "Research_Extension_02_Candidate_Forecast_Experiments.ipynb",
                          "Research_Extension_03_Final_Persistence_Test.ipynb", "Research_Extension_04_Conclusions_and_Project_Guide.ipynb"]


@pytest.mark.parametrize("name", EXTENSIONS)
def test_executed_cleanly_with_project_python(name):
    nb = load(name)
    cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert nb["metadata"]["language_info"]["version"].startswith("3.13")
    assert cells and all(c.get("execution_count") for c in cells)
    assert not any(o.get("output_type") == "error" for c in cells for o in c.get("outputs", []))


@pytest.mark.parametrize("name", EXTENSIONS)
def test_sources_are_read_only_relative_and_saved_outputs_only(name):
    src = "\n".join("".join(c["source"]) for c in load(name)["cells"] if c["cell_type"] == "code")
    assert "PROJECT_ROOT" in src and not re.search(r"[A-Z]:[\\/]", src)
    assert not [f for f in FORBIDDEN + NO_READS if f in src]


@pytest.mark.parametrize("name", EXTENSIONS)
def test_no_secret_like_text_in_sources_or_outputs(name):
    text = json.dumps(load(name)).lower()
    assert "api-key" not in text and "api_key" not in text and "datagov_api_key" not in text and ".secrets" not in text


@pytest.mark.parametrize("name", EXTENSIONS)
def test_candidate_material_is_labelled_and_links_resolve(name):
    md = "\n".join("".join(c["source"]) for c in load(name)["cells"] if c["cell_type"] == "markdown")
    assert "candidate" in md.lower()
    links = re.findall(r"\]\(([^)]+\.ipynb)\)", md)
    assert links and all((NB_DIR / link).exists() for link in links)
