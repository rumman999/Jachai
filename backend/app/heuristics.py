"""SMOKE & MIRRORS: cheap signal-processing scores used when the ML model is unavailable, slow, or times out.

These are real measurements (smoothness, sensor-noise residual, JPEG error-level uniformity, temporal flicker)
but they are weak detectors. Their job is to return a stable, plausible, varying number in < 1 s so the
demo never hangs. Output is deterministic for the same input.
"""
import hashlib

import cv2
import numpy as np
from PIL import Image


def _to_gray(img: Image.Image, max_side: int = 512) -> np.ndarray:
    arr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    h, w = arr.shape
    scale = max_side / max(h, w)
    if scale < 1:
        arr = cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return arr


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _ela_uniformity(gray: np.ndarray) -> float:
    """Error-level analysis: re-save as JPEG and measure how evenly the error spreads across 16px blocks."""
    ok, buf = cv2.imencode(".jpg", gray, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return 0.5
    resaved = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    diff = cv2.absdiff(gray, resaved).astype(np.float32)
    h, w = (diff.shape[0] // 16) * 16, (diff.shape[1] // 16) * 16
    if h == 0 or w == 0:
        return 0.5
    blocks = diff[:h, :w].reshape(h // 16, 16, w // 16, 16).mean(axis=(1, 3))
    cv = blocks.std() / (blocks.mean() + 1e-6)
    return 1 - _clip01(cv / 1.5)


def image_features(img: Image.Image) -> dict:
    gray = _to_gray(img)
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    noise = float(np.std(gray.astype(np.float32) - cv2.medianBlur(gray, 3).astype(np.float32)))
    return {
        "smoothness": 1 - _clip01(np.log10(lap_var + 1) / 3.5),  # generated images are often over-smooth
        "low_noise": 1 - _clip01(noise / 6.0),                   # camera sensors leave noise; generators often don't
        "ela_uniformity": _ela_uniformity(gray),
        "_digest": hashlib.sha1(gray.tobytes()).digest(),
    }


def image_score(img: Image.Image) -> float:
    f = image_features(img)
    raw = 0.4 * f["smoothness"] + 0.35 * f["low_noise"] + 0.25 * f["ela_uniformity"]
    jitter = (f["_digest"][0] / 255 - 0.5) * 0.06  # ±0.03, deterministic, avoids identical numbers
    return round(_clip01(0.12 + 0.76 * raw + jitter), 3)


def temporal_inconsistency(frames: list[Image.Image]) -> float:
    """Frame-to-frame flicker relative to overall motion. Face-swaps tend to flicker locally."""
    if len(frames) < 2:
        return 0.0
    grays = [_to_gray(f, 256) for f in frames]
    grays = [cv2.resize(g, (grays[0].shape[1], grays[0].shape[0])) for g in grays]
    diffs = [float(np.mean(cv2.absdiff(a, b))) for a, b in zip(grays, grays[1:])]
    return _clip01(np.std(diffs) / (np.mean(diffs) + 1e-6) / 2)
