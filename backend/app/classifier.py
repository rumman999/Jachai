"""Pretrained Hugging Face image classifier, loaded lazily and never on the request path.

If torch/transformers are missing, ENABLE_ML is off, or the model is still loading, `fake_probabilities`
returns None and the caller uses the heuristic scorer instead. The demo never waits on a model download.
"""
import logging
import re
import threading
import time
from typing import Optional

from . import config

log = logging.getLogger(__name__)

_FAKE_WORDS = {"fake", "deepfake", "artificial", "ai", "synthetic", "generated", "manipulated", "gan", "sd", "sdxl"}
_REAL_WORDS = {"real", "realism", "human", "authentic", "natural", "original", "genuine"}

_lock = threading.Lock()        # guards loading
_infer_lock = threading.Lock()  # HF pipelines are not guaranteed thread-safe
_pipe = None
_state = {"status": "not_loaded", "error": None, "load_seconds": None, "labels": None}


def status() -> dict:
    if not config.ENABLE_ML:
        return {"status": "disabled", "model": config.MODEL_ID}
    return {"model": config.MODEL_ID, **_state}


def load() -> Optional[object]:
    """Blocking load. Called from the startup warm-up thread."""
    global _pipe
    if not config.ENABLE_ML:
        return None
    with _lock:
        if _pipe is not None or _state["status"] == "unavailable":
            return _pipe
        _state["status"] = "loading"
        started = time.perf_counter()
        try:
            from transformers import pipeline  # heavy import, keep it lazy

            _pipe = pipeline("image-classification", model=config.MODEL_ID, device=-1)
            _state["labels"] = list(_pipe.model.config.id2label.values())
            _state["status"] = "warming"  # usable, but the first few inferences on a fresh container are slow
            _state["load_seconds"] = round(time.perf_counter() - started, 1)
            log.info("model %s loaded in %.1fs, labels=%s", config.MODEL_ID, _state["load_seconds"], _state["labels"])
        except Exception as exc:
            _state["status"], _state["error"] = "unavailable", repr(exc)
            log.warning("model unavailable, using heuristics: %r", exc)
    return _pipe


def load_in_background():
    if config.ENABLE_ML and _state["status"] == "not_loaded":
        threading.Thread(target=_warm_up, daemon=True, name="model-warmup").start()


def _warm_up():
    """On a fresh Railway container the first several inferences take 8 s+ (measured), which trips the job timeout.
    Burn through them here, with the same shapes real requests use, before /health reports "ready"."""
    if load() is None:
        return
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(0)
    photo = Image.fromarray(rng.integers(0, 255, (768, 1024, 3), dtype=np.uint8))
    face = photo.crop((300, 200, 600, 500))
    started = time.perf_counter()
    for batch in ([photo], [photo, face], [photo, face], [photo] * 6):  # single image, image+face, video frames
        try:
            fake_probabilities(batch)
        except Exception as exc:
            log.warning("warm-up inference failed: %r", exc)
            break
    _state["warmup_seconds"] = round(time.perf_counter() - started, 1)
    _state["status"] = "ready"
    log.info("model warm in %.1fs", _state["warmup_seconds"])


def _fake_score(predictions: list[dict]) -> float:
    scores = {p["label"]: float(p["score"]) for p in predictions}
    if config.FAKE_LABEL:
        return scores.get(config.FAKE_LABEL, 0.0)
    fake = real = 0.0
    for label, score in scores.items():
        words = set(re.split(r"[^a-z0-9]+", label.lower()))
        if words & _FAKE_WORDS:
            fake += score
        elif words & _REAL_WORDS:
            real += score
    if fake == 0 and real == 0:
        # Unrecognised labels (e.g. LABEL_0/LABEL_1): assume the last class is "fake". Set FAKE_LABEL to be sure.
        return list(scores.values())[-1]
    return fake if fake > 0 else 1 - real


def fake_probabilities(images: list) -> Optional[list[float]]:
    """Returns one 0–1 fake probability per PIL image, or None if the model isn't ready."""
    if _pipe is None or not images:
        return None
    with _infer_lock:
        outputs = _pipe(images, top_k=None, batch_size=len(images))
    if outputs and isinstance(outputs[0], dict):  # single image → flat list
        outputs = [outputs]
    return [_fake_score(o) for o in outputs]
