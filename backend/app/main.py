import logging
import os
import tempfile
from contextlib import asynccontextmanager
from functools import partial

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, classifier, config, hoax_matcher, jobs, media_pipeline, mock, ocr, text_check
from .schemas import JobCreated, Result, TextRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("jachai")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    hoax_matcher.entries()
    ocr.status()
    if not config.MOCK_MODE:
        classifier.load_in_background()  # pre-warm so the first judge's request isn't the slow one
    log.info("ready: mock=%s ml=%s", config.MOCK_MODE, config.ENABLE_ML)
    yield


app = FastAPI(title="Jachai verification API", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "mock_mode": config.MOCK_MODE,
        "engines": {"visual": classifier.status(), "ocr": ocr.status(), "hoax_db": hoax_matcher.status()},
    }


@app.post("/verify/media", response_model=JobCreated, status_code=202)
async def verify_media(background: BackgroundTasks, file: UploadFile = File(...)):
    kind = media_pipeline.detect_kind(file.content_type, file.filename)
    if kind is None:
        raise HTTPException(415, f"Unsupported file type: {file.content_type or file.filename}")

    if config.MOCK_MODE:
        return JobCreated(job_id=mock.submit(kind))

    suffix = os.path.splitext(file.filename or "")[1] or (".mp4" if kind == "video" else ".jpg")
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="jachai_") as tmp:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                tmp.close()
                os.remove(tmp.name)
                raise HTTPException(413, f"File larger than {config.MAX_UPLOAD_MB} MB")
            tmp.write(chunk)
    if size == 0:
        os.remove(tmp.name)
        raise HTTPException(400, "Empty file")

    job = jobs.store.create(kind)
    background.add_task(jobs.run_job, job,
                        work=partial(media_pipeline.analyze_media, tmp.name, kind),
                        fallback=partial(media_pipeline.fallback_media, tmp.name, kind),
                        cleanup_path=tmp.name)
    log.info("job %s: %s %.1f KB", job.id, kind, size / 1024)
    return JobCreated(job_id=job.id)


@app.post("/verify/text", response_model=JobCreated, status_code=202)
async def verify_text(body: TextRequest, background: BackgroundTasks):
    if config.MOCK_MODE:
        return JobCreated(job_id=mock.submit("text"))
    job = jobs.store.create("text")
    background.add_task(jobs.run_job, job,
                        work=partial(text_check.check_claim, body.text),
                        fallback=text_check.fallback_claim)
    return JobCreated(job_id=job.id)


@app.get("/result/{job_id}", response_model=Result)
def result(job_id: str):
    if config.MOCK_MODE:
        return mock.result(job_id)
    job = jobs.store.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown or expired job_id")
    if job.status == "pending":
        return {"job_id": job.id, "status": "pending", "kind": job.kind}
    return {**(job.result or {}), "job_id": job.id, "status": job.status, "kind": job.kind}
