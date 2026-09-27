# API Contract (locked Day 1)

Base URL: the deployed HTTPS URL (Railway/Render). Never `localhost` in a build you hand to someone else.

| Endpoint | Method | Body | Returns |
|---|---|---|---|
| `/verify/media` | POST multipart | form field `file` (image/* or video/*) | `202` → `JobCreated` |
| `/verify/text` | POST json | `{"text": "..."}` | `202` → `JobCreated` |
| `/result/{job_id}` | GET | — | `200` → `Result` (poll every 1.5 s until `status != "pending"`) |
| `/health` | GET | — | `200` → engine status |

## JobCreated

```json
{ "job_id": "3f2a…", "status": "pending", "poll_after_ms": 1500 }
```

## Result

```json
{
  "job_id": "3f2a…",
  "status": "done",                 // "pending" | "done" | "error"
  "kind": "image",                  // "image" | "video" | "text"
  "verdict": "red",                 // "red" | "green"  ← the only thing the big screen needs
  "label": "AI_GENERATED",          // AI_GENERATED | LIKELY_AUTHENTIC | KNOWN_HOAX | NO_KNOWN_MATCH
  "confidence": 0.87,               // confidence in the shown verdict, 0–1
  "fake_probability": 0.87,         // raw visual score (null for text)
  "title":       { "en": "Likely fake / AI-generated", "bn": "সম্ভবত ভুয়া / এআই-তৈরি" },
  "explanation": { "en": "…", "bn": "…" },
  "engine": "model",                // model | heuristic | fallback | hoax_db | override | mock
  "frames_analyzed": null,          // int for video
  "matched_claim": null,            // { id, claim_en, claim_bn, similarity } for KNOWN_HOAX
  "extracted_text": null,           // OCR text when a screenshot went through the claim path
  "elapsed_ms": 1840
}
```

Rules:
- `verdict`, `title`, `explanation` are always present when `status == "done"`.
- The server always answers within `JOB_TIMEOUT_S` (default 8 s): on timeout it returns a heuristic verdict with `engine: "fallback"`, so the client should never need its own verdict logic.
- Unknown / expired `job_id` → `404`. Unsupported file type → `415`. File too large → `413`.
- Fields are only ever **added**, never renamed or removed.
