"""Run at Docker build time so the model weights are baked into the image (no cold-start download on stage)."""
from . import config

if __name__ == "__main__":
    try:
        from transformers import pipeline

        pipeline("image-classification", model=config.MODEL_ID)
        print(f"prefetched {config.MODEL_ID}")
    except Exception as exc:  # don't fail the build; the server falls back to heuristics
        print(f"WARNING: could not prefetch {config.MODEL_ID}: {exc!r}")
    if config.ENABLE_EMBEDDINGS:
        try:
            from sentence_transformers import SentenceTransformer

            SentenceTransformer(config.EMBED_MODEL_ID)
        except Exception as exc:
            print(f"WARNING: could not prefetch {config.EMBED_MODEL_ID}: {exc!r}")
