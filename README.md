# Jachai (যাচাই): AI-generated content & hoax detector

Android share-sheet app + FastAPI backend for the AI Congress 2026 Buildfest.
Share a photo, video or message to **Jachai** → full-screen **Red** (fake / known hoax) or **Green** verdict, in Bengali and English.

```
android/   Native Java app (min SDK 24). Share-sheet entry point → VerdictActivity
backend/   FastAPI service: /verify/media, /verify/text, /result/{job_id}, /health
docs/      API_CONTRACT.md (locked Day 1)
```

## Status against the 5-day plan

| Day | Deliverable | State |
|---|---|---|
| 1 | 4 contract endpoints, mock mode (`MOCK_MODE=true`: fixed job id, alternating red/green) | ✅ tested |
| 1 | Android project, `ACTION_SEND`/`SEND_MULTIPLE` filters for `image/*`, `video/*`, `text/plain`, spinner → Red/Green screen, Retrofit client | ✅ written, **needs first build in Android Studio** |
| 1 | Deploy to Railway/Render | ⏳ configs ready (`backend/Dockerfile`, `backend/railway.json`, `render.yaml`), needs your account |
| 2 | Image path: OpenCV preprocess + Haar face crop + HF classifier (`prithivMLmods/Deep-Fake-Detector-v2-Model`) | ✅ ~0.15 s/image on CPU |
| 2 | Video path: 6 evenly spaced frames, face-crop, mean/max aggregation | ✅ ~1.5 s/clip |
| 2 | Heuristic fallback + 8 s server-side timeout → verdict always returned | ✅ tested |
| 3 | OCR (Tesseract ben+eng) + UI-chrome cleaning; text-heavy images go down the claim path | ✅ code + tests. Tesseract ships in the Docker image; not installed on this PC |
| 3 | 45-entry bilingual hoax DB + fuzzy matcher (IDF-weighted token coverage + rapidfuzz; optional LaBSE-style embeddings) | ✅ calibrated: hoaxes ≥ 0.63, real news ≤ 0.47, threshold 0.58 |
| 3 | Bilingual explanation generated server-side | ✅ |

## Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
# optional, real model (otherwise heuristics):
.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\pip install -r requirements-ml.txt

.venv\Scripts\python -m pytest -q                          # 34 tests
.venv\Scripts\python scripts\benchmark_model.py            # Day-2 latency check
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Tunables are environment variables; see `backend/.env.example`. The important ones:

- `MOCK_MODE=true` gives the Day 1 behaviour (the demo still works if everything else breaks).
- `ENABLE_ML=false` uses the heuristic scorer only, for hosts with 512 MB RAM.
- `HOAX_THRESHOLD` and `FAKE_THRESHOLD` are the verdict cut-offs.

**OCR on Windows (optional, for local testing):** install Tesseract from the UB Mannheim build, tick *Bengali* under additional languages, then set `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`. `/health` shows `engines.ocr.available`.

### Deploy (Railway, recommended)

1. Push this repo to GitHub → Railway → *New project → Deploy from repo*, set **root directory** to `backend`.
2. Railway picks up `railway.json` + `Dockerfile` (includes Tesseract-Bengali and bakes the model into the image).
3. Give the service ≥ 1 GB RAM for the model. Otherwise set `ENABLE_ML=false`.
4. *Settings → Networking → Generate domain*, then open `https://<domain>/health` **from a phone on mobile data**.

Render: `render.yaml` at the repo root. The free plan (512 MB) runs with `ENABLE_ML=false`.

## Android

1. Open `android/` in Android Studio (it will download the SDK/Gradle on first sync).
2. Add your backend URL to `android/local.properties`:
   ```
   api.baseUrl=https://<your-domain>/
   ```
   (It can also be changed at runtime on the app's home screen, e.g. `http://192.168.x.x:8000` for LAN testing.)
3. Run on a **real phone**, then share an image from Gallery/WhatsApp and pick *Check with Jachai*.

## Demo safety nets

- **Pin rehearsed files:** `python scripts/add_override.py demo/fake.mp4 red`, or `… hoax.png red --hoax-id padma-bridge-heads`. The file's SHA-256 always gets that verdict.
- **Check the hoax DB:** `backend/data/hoaxes.json` is a demo database. Before the pitch, check every `fact_en`/`fact_bn` line against a Bangladeshi fact-checker (e.g. Rumor Scanner, Dismislab, AFP Fact Check Bangla) and add source links.
- **Re-run the calibration tests** after editing the hoax DB: `pytest tests/test_matcher_calibration.py`.
