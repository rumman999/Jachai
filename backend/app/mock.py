"""Day 1 mock: fixed job id, verdict alternates red/green on every submission. Enable with MOCK_MODE=1."""
import threading
import time

from . import explain, hoax_matcher

MOCK_JOB_ID = "mock-job-0001"
_lock = threading.Lock()
_state = {"count": 0, "kind": "image", "submitted": 0.0}


def submit(kind: str) -> str:
    with _lock:
        _state["count"] += 1
        _state["kind"] = kind
        _state["submitted"] = time.time()
    return MOCK_JOB_ID


def result(job_id: str) -> dict:
    with _lock:
        count, kind, submitted = _state["count"], _state["kind"], _state["submitted"]
    base = {"job_id": job_id, "kind": kind}
    # Stay "pending" for the first second so the client's polling loop is exercised.
    if time.time() - submitted < 1.0:
        return {**base, "status": "pending"}

    red = count % 2 == 1
    if kind == "text":
        entries = hoax_matcher.entries()
        payload = (explain.hoax_result(entries[0], 0.93) if red and entries
                   else explain.no_match_result(0.1))
    else:
        payload = explain.visual_result(kind, 0.91 if red else 0.12, "mock",
                                        frames=6 if kind == "video" else None)
    payload.update(engine="mock", elapsed_ms=1200)
    return {**base, **payload, "status": "done"}
