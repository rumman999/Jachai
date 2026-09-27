import io

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config, hoax_matcher, text_check
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _result(client, job_id):
    # TestClient runs background tasks before returning, so one poll is enough.
    r = client.get(f"/result/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done", body
    assert body["verdict"] in {"red", "green"}
    assert body["explanation"]["en"] and body["explanation"]["bn"]
    assert body["title"]["en"] and body["title"]["bn"]
    return body


def _png(noise: bool) -> bytes:
    rng = np.random.default_rng(0)
    arr = np.tile(np.linspace(0, 255, 256, dtype=np.uint8), (256, 1))
    arr = np.stack([arr] * 3, axis=-1)
    if noise:
        arr = np.clip(arr + rng.normal(0, 25, arr.shape), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["engines"]["hoax_db"]["entries"] >= 40


def test_text_known_hoax_bengali(client):
    r = client.post("/verify/text", json={"text": "শুনলাম পদ্মা সেতুতে মানুষের মাথা লাগবে, ছেলেধরারা শিশুদের মাথা সংগ্রহ করছে!"})
    assert r.status_code == 202
    body = _result(client, r.json()["job_id"])
    assert body["verdict"] == "red" and body["label"] == "KNOWN_HOAX"
    assert body["matched_claim"]["id"] == "padma-bridge-heads"


def test_text_known_hoax_english_paraphrase(client):
    r = client.post("/verify/text", json={"text": "URGENT: 5G towers are spreading the corona virus, share with everyone"})
    body = _result(client, r.json()["job_id"])
    assert body["label"] == "KNOWN_HOAX" and body["matched_claim"]["id"] == "5g-corona"


def test_text_no_match_is_cautious_green(client):
    r = client.post("/verify/text", json={"text": "Bangladesh won the cricket match against Sri Lanka by five wickets today"})
    body = _result(client, r.json()["job_id"])
    assert body["verdict"] == "green" and body["label"] == "NO_KNOWN_MATCH"
    assert body["confidence"] <= 0.6


@pytest.mark.parametrize("text", ["coronavirus", "padma bridge", "vaccine"])
def test_short_inputs_do_not_false_match(text):
    match = hoax_matcher.best_match(text)
    assert match is None or match.score < config.HOAX_THRESHOLD, (text, match)


def test_ocr_text_cleaning_strips_chrome():
    raw = """10:45 AM  87%
    Rahim Uddin · 2h ·
    থানকুনি পাতা খেলে করোনাভাইরাস ভালো হয়, সবাই শেয়ার করুন
    1.2K likes  345 comments
    Like
    Comment
    Share
    https://example.com/xyz"""
    cleaned = text_check.clean_ocr_text(raw)
    assert "Like" not in cleaned.split() and "https" not in cleaned and "10:45" not in cleaned
    result = text_check.check_claim(cleaned, extracted=True)
    assert result["label"] == "KNOWN_HOAX" and result["matched_claim"]["id"] == "thankuni-corona"


def test_media_image(client):
    r = client.post("/verify/media", files={"file": ("photo.png", _png(noise=True), "image/png")})
    assert r.status_code == 202
    body = _result(client, r.json()["job_id"])
    assert body["kind"] == "image" and body["engine"] == "heuristic"
    assert 0 <= body["fake_probability"] <= 1


def test_heuristic_separates_smooth_from_noisy(client):
    smooth = _result(client, client.post("/verify/media", files={"file": ("a.png", _png(False), "image/png")}).json()["job_id"])
    noisy = _result(client, client.post("/verify/media", files={"file": ("b.png", _png(True), "image/png")}).json()["job_id"])
    assert smooth["fake_probability"] > noisy["fake_probability"]


def test_media_video(client, tmp_path):
    path = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 120))
    rng = np.random.default_rng(1)
    for i in range(40):
        writer.write(rng.integers(0, 255, (120, 160, 3), dtype=np.uint8))
    writer.release()
    r = client.post("/verify/media", files={"file": ("clip.mp4", path.read_bytes(), "video/mp4")})
    body = _result(client, r.json()["job_id"])
    assert body["kind"] == "video" and body["frames_analyzed"] == config.VIDEO_FRAMES


def test_undecodable_media_still_returns_verdict(client):
    r = client.post("/verify/media", files={"file": ("broken.jpg", b"not really a jpeg", "image/jpeg")})
    body = _result(client, r.json()["job_id"])
    assert body["engine"] == "fallback"


def test_unsupported_type(client):
    r = client.post("/verify/media", files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 415


def test_unknown_job(client):
    assert client.get("/result/does-not-exist").status_code == 404


def test_mock_mode_alternates(client, monkeypatch):
    import app.mock as mock

    monkeypatch.setattr(config, "MOCK_MODE", True)
    verdicts = []
    for _ in range(2):
        job_id = client.post("/verify/media", files={"file": ("x.jpg", b"x", "image/jpeg")}).json()["job_id"]
        assert job_id == mock.MOCK_JOB_ID
        assert client.get(f"/result/{job_id}").json()["status"] == "pending"
        mock._state["submitted"] -= 5  # skip the simulated delay
        verdicts.append(_result(client, job_id)["verdict"])
    assert set(verdicts) == {"red", "green"}
