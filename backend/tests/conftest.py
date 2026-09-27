import os
import sys
from pathlib import Path

# Deterministic, fast tests: no model download, real (non-mock) pipeline.
os.environ.setdefault("ENABLE_ML", "false")
os.environ.setdefault("MOCK_MODE", "false")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
