"""Day 2 checkpoint: does the model load, what labels does it use, and how fast is CPU inference?

    python scripts/benchmark_model.py [MODEL_ID]
If per-image latency is > ~4 s, set ENABLE_ML=false and demo on the heuristic scorer (plan's cut rule #2).
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if len(sys.argv) > 1:
    os.environ["MODEL_ID"] = sys.argv[1]

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app import classifier  # noqa: E402

t0 = time.perf_counter()
classifier.load()
print("status:", classifier.status(), f"(total {time.perf_counter() - t0:.1f}s)")
if classifier.status()["status"] != "ready":
    sys.exit(1)

rng = np.random.default_rng(0)
imgs = [Image.fromarray(rng.integers(0, 255, (512, 512, 3), dtype=np.uint8)) for _ in range(6)]
classifier.fake_probabilities(imgs[:1])  # warm-up
for n in (1, 6):
    t = time.perf_counter()
    probs = classifier.fake_probabilities(imgs[:n])
    dt = time.perf_counter() - t
    print(f"{n} image(s): {dt:.2f}s total, {dt / n:.2f}s each, probs={[round(p, 3) for p in probs]}")
