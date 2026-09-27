"""Image + video analysis. Images first go through OCR: a text-heavy image is a claim screenshot, not a photo."""
import logging
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import classifier, config, explain, heuristics, ocr, overrides, text_check

log = logging.getLogger(__name__)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".3gp", ".mkv", ".webm", ".avi", ".m4v"}

try:
    _face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
except AttributeError:  # OpenCV builds without the legacy objdetect module
    _face_cascade = None
    log.warning("Haar cascade unavailable: face cropping disabled")


def detect_kind(content_type: Optional[str], filename: Optional[str]) -> Optional[str]:
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("video/"):
        return "video"
    ext = "." + (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def load_image(path: str, max_side: int = 1024) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(path))
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    return img


def face_crop(img: Image.Image, margin: float = 0.3) -> Optional[Image.Image]:
    if _face_cascade is None:
        return None
    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
    faces = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    mx, my = int(w * margin), int(h * margin)
    return img.crop((max(0, x - mx), max(0, y - my), min(img.width, x + w + mx), min(img.height, y + h + my)))


def _score(images: list[Image.Image]) -> tuple[list[float], str]:
    probs = classifier.fake_probabilities(images)
    if probs is not None:
        return probs, "model"
    return [heuristics.image_score(im) for im in images], "heuristic"


def analyze_image(path: str) -> dict:
    img = load_image(path)

    raw_text = ocr.extract_text(img)
    cleaned = text_check.clean_ocr_text(raw_text)
    if text_check.is_text_heavy(cleaned):
        return text_check.check_claim(cleaned, extracted=True)

    variants = [img]
    face = face_crop(img)
    if face is not None:
        variants.append(face)
    probs, engine = _score(variants)
    return explain.visual_result("image", float(np.mean(probs)), engine, extracted_text=cleaned or None)


def extract_frames(path: str, count: int) -> list[Image.Image]:
    cap = cv2.VideoCapture(path)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frames = []
        if total > 0:
            # Skip the very first/last frame: they're often black or a title card.
            for idx in np.linspace(0, total - 1, count + 2)[1:-1].astype(int):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
                ok, frame = cap.read()
                if ok:
                    frames.append(frame)
        if not frames:  # container without a frame count: read sequentially
            while len(frames) < count * 10:
                ok, frame = cap.read()
                if not ok:
                    break
                frames.append(frame)
            frames = frames[:: max(1, len(frames) // count)][:count]
    finally:
        cap.release()
    out = []
    for f in frames:
        im = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        im.thumbnail((720, 720))
        out.append(im)
    return out


def analyze_video(path: str, heuristic_only: bool = False) -> dict:
    frames = extract_frames(path, config.VIDEO_FRAMES)
    if not frames:
        raise ValueError("no decodable frames")
    # Deepfakes live in the face: classify the face crop when there is one.
    inputs = []
    for f in frames:
        face = face_crop(f)
        inputs.append(face if face is not None else f)
    if heuristic_only:
        probs, engine = [heuristics.image_score(im) for im in inputs], "heuristic"
    else:
        probs, engine = _score(inputs)
    p = 0.6 * float(np.mean(probs)) + 0.4 * float(np.max(probs))
    if engine == "heuristic":
        p = min(0.97, p + 0.15 * heuristics.temporal_inconsistency(inputs))
    return explain.visual_result("video", p, engine, frames=len(frames))


def analyze_media(path: str, kind: str) -> dict:
    pinned = overrides.lookup(path, kind)
    if pinned:
        return pinned
    return analyze_image(path) if kind == "image" else analyze_video(path)


def fallback_media(path: str, kind: str) -> dict:
    """Heuristic-only path used after a timeout/crash. No OCR, no model: must finish in well under 3 s."""
    if kind == "video":
        return analyze_video(path, heuristic_only=True)
    return explain.visual_result("image", heuristics.image_score(load_image(path, 768)), "heuristic")
