import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(PROJECT_ROOT)  # pipeline paths are project-root relative, like the notebooks
sys.path.insert(0, str(PROJECT_ROOT))
