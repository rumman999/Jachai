"""All tunables come from environment variables so the demo can be re-tuned without a redeploy of code."""
import os
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Day 1 behaviour: fixed job id, alternating red/green, zero inference.
MOCK_MODE = _bool("MOCK_MODE", False)

# Visual pipeline
ENABLE_ML = _bool("ENABLE_ML", True)
MODEL_ID = os.getenv("MODEL_ID", "prithivMLmods/Deep-Fake-Detector-v2-Model")
FAKE_LABEL = os.getenv("FAKE_LABEL", "")  # force which model label means "fake" if auto-detection guesses wrong
FAKE_THRESHOLD = float(os.getenv("FAKE_THRESHOLD", "0.5"))
VIDEO_FRAMES = int(os.getenv("VIDEO_FRAMES", "6"))

# Text / claim pipeline
OCR_LANGS = os.getenv("OCR_LANGS", "ben+eng")
OCR_TIMEOUT_S = float(os.getenv("OCR_TIMEOUT_S", "5"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
# Tuned on tests/test_matcher_calibration.py: hoax paraphrases score ≥ 0.63, unrelated news ≤ 0.47.
HOAX_THRESHOLD = float(os.getenv("HOAX_THRESHOLD", "0.58"))
ENABLE_EMBEDDINGS = _bool("ENABLE_EMBEDDINGS", False)
EMBED_MODEL_ID = os.getenv("EMBED_MODEL_ID", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# Job handling
JOB_TIMEOUT_S = float(os.getenv("JOB_TIMEOUT_S", "8"))
JOB_TTL_S = int(os.getenv("JOB_TTL_S", "900"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
