"""Pin the verdict for a rehearsed demo file.

    python scripts/add_override.py path/to/fake_video.mp4 red --confidence 0.94
    python scripts/add_override.py path/to/real_photo.jpg green
    python scripts/add_override.py path/to/hoax_screenshot.png red --hoax-id padma-bridge-heads
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.overrides import OVERRIDES_FILE, file_sha256  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("file")
parser.add_argument("verdict", choices=["red", "green"])
parser.add_argument("--confidence", type=float, default=0.93)
parser.add_argument("--hoax-id")
args = parser.parse_args()

data = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8")) if OVERRIDES_FILE.exists() else {}
entry = {"verdict": args.verdict, "confidence": args.confidence, "file": Path(args.file).name}
if args.hoax_id:
    entry["hoax_id"] = args.hoax_id
data[file_sha256(args.file)] = entry
OVERRIDES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"pinned {args.file} -> {entry}")
