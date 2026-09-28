"""Compare candidate Hugging Face detectors on labelled samples (samples/real, samples/fake). Runs locally.

    python scripts/compare_models.py ../samples [MODEL_ID ...]

For each model prints per-file scores and:
  ranking  = share of (real, fake) pairs where the fake scores higher (1.0 perfect, 0.5 = coin flip)
  best     = accuracy at the best single threshold, and that threshold
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app import classifier, media_pipeline  # noqa: E402
from calibrate import best_threshold  # noqa: E402

DEFAULT_MODELS = [
    "prithivMLmods/Deep-Fake-Detector-v2-Model",
    "Organika/sdxl-detector",
    "umm-maybe/AI-image-detector",
    "dima806/ai_vs_real_image_detection",
    "Ateeqq/ai-vs-human-image-detector",
]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def load_inputs(folder: Path) -> list[tuple[str, list]]:
    items = []
    for path in sorted(folder.glob("*")):
        if path.suffix.lower() in IMAGE_EXTS:
            img = media_pipeline.load_image(str(path))
            face = media_pipeline.face_crop(img)
            items.append((path.name, [img] + ([face] if face is not None else [])))
        elif path.suffix.lower() in media_pipeline.VIDEO_EXTS:
            items.append((path.name, media_pipeline.extract_frames(str(path), 6)))
    return items


def main():
    folder = Path(sys.argv[1])
    models = sys.argv[2:] or DEFAULT_MODELS
    data = {g: load_inputs(folder / g) for g in ("real", "fake")}
    print(f"{len(data['real'])} real, {len(data['fake'])} fake\n")

    from transformers import pipeline

    summary = []
    for model_id in models:
        print(f"== {model_id}")
        try:
            t = time.perf_counter()
            pipe = pipeline("image-classification", model=model_id, device=-1)
            print(f"   labels={list(pipe.model.config.id2label.values())}  load {time.perf_counter() - t:.0f}s")
        except Exception as exc:
            print(f"   could not load: {exc!r}\n")
            continue
        scores = {"real": [], "fake": []}
        started = time.perf_counter()
        for group, items in data.items():
            for name, images in items:
                preds = pipe(images, top_k=None)
                p = sum(classifier._fake_score(x) for x in preds) / len(preds)
                scores[group].append(p)
                print(f"   {group:<5} {p:.3f}  {name[:70]}")
        n = sum(len(v) for v in data.values())
        per_item = (time.perf_counter() - started) / max(1, n)
        pairs = [(r, f) for r in scores["real"] for f in scores["fake"]]
        ranking = sum(f > r for r, f in pairs) / len(pairs) if pairs else 0
        thr, correct = best_threshold(scores["real"], scores["fake"])
        summary.append((ranking, correct, n, thr, per_item, model_id))
        print(f"   ranking={ranking:.2f}  best={correct}/{n} at {thr}  {per_item:.2f}s/item\n")
        del pipe

    print("== summary (best first)")
    for ranking, correct, n, thr, per_item, model_id in sorted(summary, reverse=True):
        print(f"   ranking={ranking:.2f}  best={correct}/{n} @ {thr:<6} {per_item:.2f}s/item  {model_id}")


if __name__ == "__main__":
    main()
