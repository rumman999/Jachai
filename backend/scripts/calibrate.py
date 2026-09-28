"""Score a folder of labelled samples against a running server and suggest FAKE_THRESHOLD.

    python scripts/calibrate.py ../samples --url https://jachai-api-production.up.railway.app

Expects   samples/real/*   samples/fake/*   (images or videos)   and optionally   samples/screenshots/*
Sends each file to /verify/media exactly like the app does, so it measures the real deployment.
"""
import argparse
import json
import mimetypes
import sys
import time
import urllib.request
import uuid
from pathlib import Path

MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".mp4", ".mov", ".3gp", ".mkv", ".webm", ".m4v"}


def _request(url: str, data: bytes = None, headers: dict = None) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verify(base: str, path: Path) -> dict:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    started = time.time()
    job = _request(f"{base}/verify/media", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    while True:
        time.sleep(1.5)
        result = _request(f"{base}/result/{job['job_id']}")
        if result["status"] != "pending":
            result["wall_s"] = round(time.time() - started, 1)
            return result


def best_threshold(real: list[float], fake: list[float]) -> tuple[float, int]:
    candidates = sorted(set(real + fake + [0.5]))
    scored = []
    for t in candidates:
        correct = sum(p < t for p in real) + sum(p >= t for p in fake)
        scored.append((correct, -abs(t - 0.5), t))
    correct, _, t = max(scored)
    return round(t, 3), correct


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--url", default="https://jachai-api-production.up.railway.app")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    sys.stdout.reconfigure(encoding="utf-8")

    health = _request(f"{base}/health")
    print(f"server v{health['version']}  visual={health['engines']['visual'].get('status')}  "
          f"ocr={health['engines']['ocr'].get('available')}\n")

    scores = {"real": [], "fake": []}
    for group in ("real", "fake", "screenshots"):
        folder = args.folder / group
        files = sorted(p for p in folder.glob("*") if p.suffix.lower() in MEDIA_EXTS) if folder.exists() else []
        if not files:
            continue
        print(f"== {group} ({len(files)})")
        for path in files:
            try:
                r = verify(base, path)
            except Exception as exc:
                print(f"  ERROR     {path.name}: {exc}")
                continue
            p = r.get("fake_probability")
            if group in scores and p is not None and r.get("label") in ("AI_GENERATED", "LIKELY_AUTHENTIC"):
                scores[group].append(p)
            extra = f"  matched={r['matched_claim']['id']}" if r.get("matched_claim") else ""
            if group == "screenshots" and r.get("extracted_text"):
                extra += f"  ocr=\"{r['extracted_text'][:60]}…\""
            print(f"  {r.get('verdict', '?'):<6} {r.get('label', '?'):<17} p_fake={p if p is not None else '-':<6} "
                  f"engine={r.get('engine')}  {r['wall_s']}s  {path.name}{extra}")
        print()

    if scores["real"] and scores["fake"]:
        t, correct = best_threshold(scores["real"], scores["fake"])
        total = len(scores["real"]) + len(scores["fake"])
        now = sum(p < 0.5 for p in scores["real"]) + sum(p >= 0.5 for p in scores["fake"])
        print(f"real p_fake: min {min(scores['real']):.3f}  max {max(scores['real']):.3f}")
        print(f"fake p_fake: min {min(scores['fake']):.3f}  max {max(scores['fake']):.3f}")
        print(f"current threshold 0.5 → {now}/{total} correct")
        print(f"suggested FAKE_THRESHOLD={t} → {correct}/{total} correct")


if __name__ == "__main__":
    main()
