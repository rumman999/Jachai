"""Run 5–10 minutes before walking on stage: wakes the server, waits for the model, and sends one of each request
so nothing on stage is a "first" request.

    python scripts/prewarm.py [--url https://jachai-api-production.up.railway.app] [--image demo/fake.jpg]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate import _request, verify  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://jachai-api-production.up.railway.app")
    parser.add_argument("--image", type=Path, help="a demo image/video to push through the media path once")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    sys.stdout.reconfigure(encoding="utf-8")

    deadline = time.time() + 180
    while True:
        try:
            health = _request(f"{base}/health")
            visual = health["engines"]["visual"]["status"]
            print(f"health ok · visual={visual} · ocr={health['engines']['ocr']['available']} · mock={health['mock_mode']}")
            if visual in ("ready", "disabled", "unavailable") or time.time() > deadline:
                break
        except Exception as exc:
            print(f"waiting for server… ({exc.__class__.__name__})")
            if time.time() > deadline:
                sys.exit("server did not come up in 3 minutes: check Railway")
        time.sleep(3)
    if visual != "ready":
        print(f"WARNING: visual model is '{visual}' - photo verdicts will use the heuristic fallback")

    started = time.time()
    job = _request(f"{base}/verify/text", json.dumps({"text": "5G towers spread coronavirus"}).encode(),
                   {"Content-Type": "application/json"})
    while (r := _request(f"{base}/result/{job['job_id']}"))["status"] == "pending":
        time.sleep(1)
    print(f"text path: {r['verdict']} {r['label']} in {time.time() - started:.1f}s")

    if args.image:
        r = verify(base, args.image)
        print(f"media path: {r['verdict']} {r['label']} engine={r['engine']} in {r['wall_s']}s")
    print("warm. Keep the app open on the phone and go.")


if __name__ == "__main__":
    main()
