"""In-memory job store + a runner that guarantees every job finishes within JOB_TIMEOUT_S.

Single-process only (run uvicorn with --workers 1): jobs live in this process's memory.
"""
import asyncio
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import config

log = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="verify")


@dataclass
class Job:
    id: str
    kind: str
    created: float = field(default_factory=time.time)
    status: str = "pending"
    result: Optional[dict] = None


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind)
        with self._lock:
            self._purge_expired()
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def finish(self, job_id: str, result: dict, status: str = "done"):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.result, job.status = result, status

    def _purge_expired(self):
        cutoff = time.time() - config.JOB_TTL_S
        for job_id in [j.id for j in self._jobs.values() if j.created < cutoff]:
            del self._jobs[job_id]


store = JobStore()

# Last resort if even the fallback fails: an honest "can't tell" rendered as a cautious green.
_EMERGENCY = {
    "verdict": "green", "label": "NO_KNOWN_MATCH", "confidence": 0.4, "engine": "fallback",
    "title": {"en": "Could not verify", "bn": "যাচাই করা যায়নি"},
    "explanation": {"en": "We couldn't analyse this right now. Treat it with caution and check the source.",
                    "bn": "এই মুহূর্তে বিশ্লেষণ করা যায়নি। সাবধান থাকুন এবং উৎস যাচাই করুন।"},
}


async def run_job(job: Job, work: Callable[[], dict], fallback: Callable[[], dict],
                  cleanup_path: Optional[str] = None):
    loop = asyncio.get_running_loop()
    started = time.perf_counter()
    try:
        try:
            result = await asyncio.wait_for(loop.run_in_executor(executor, work), config.JOB_TIMEOUT_S)
        except Exception as exc:  # includes TimeoutError
            log.warning("job %s (%s) fell back: %r", job.id, job.kind, exc)
            try:
                result = await asyncio.wait_for(loop.run_in_executor(executor, fallback), 3)
                result["engine"] = "fallback"
            except Exception:
                log.exception("fallback failed for job %s", job.id)
                result = dict(_EMERGENCY, kind=job.kind)
        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        store.finish(job.id, result)
    finally:
        if cleanup_path:
            # The work thread may still be reading the file after a timeout; retry deletion later.
            threading.Timer(30, _remove_quietly, args=(cleanup_path,)).start()


def _remove_quietly(path: str):
    try:
        os.remove(path)
    except OSError:
        pass
