FROM python:3.12-slim

# INSTALL_ML=0 builds a small heuristics-only image (e.g. for a 512 MB free tier).
ARG INSTALL_ML=1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/app/.hf-cache

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-ben libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install -r requirements.txt \
 && if [ "$INSTALL_ML" = "1" ]; then \
      pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements-ml.txt; \
    fi

COPY app ./app
COPY data ./data
COPY scripts ./scripts
# Bake model weights into the image so there is no download on the first request.
RUN if [ "$INSTALL_ML" = "1" ]; then python -m app.prefetch; fi

ENV PORT=8000
EXPOSE 8000
# One worker: the job store is in-process memory.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
