"""Builds the bilingual (bn + en) verdict payloads. Every verdict the API returns goes through here."""
from typing import Optional

from . import config

_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

TITLES = {
    "AI_GENERATED": {"en": "Likely fake / AI-generated", "bn": "সম্ভবত ভুয়া / এআই-তৈরি"},
    "LIKELY_AUTHENTIC": {"en": "Likely authentic", "bn": "সম্ভবত আসল"},
    "KNOWN_HOAX": {"en": "Known hoax", "bn": "পরিচিত গুজব"},
    "NO_KNOWN_MATCH": {"en": "No known hoax match", "bn": "পরিচিত কোনো গুজবের সাথে মিল নেই"},
}
VERDICTS = {"AI_GENERATED": "red", "KNOWN_HOAX": "red", "LIKELY_AUTHENTIC": "green", "NO_KNOWN_MATCH": "green"}


def bn_num(value) -> str:
    return str(value).translate(_BN_DIGITS)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _payload(label: str, confidence: float, explanation: dict, engine: str, **extra) -> dict:
    return {
        "verdict": VERDICTS[label],
        "label": label,
        "confidence": round(_clip(confidence), 3),
        "title": TITLES[label],
        "explanation": explanation,
        "engine": engine,
        **extra,
    }


def visual_result(kind: str, fake_prob: float, engine: str, frames: Optional[int] = None,
                  extracted_text: Optional[str] = None) -> dict:
    fake_prob = _clip(fake_prob)
    is_fake = fake_prob >= config.FAKE_THRESHOLD
    what_en = "video" if kind == "video" else "image"
    what_bn = "ভিডিওতে" if kind == "video" else "ছবিতে"
    frames_en = f" (checked {frames} frames)" if frames else ""
    frames_bn = f" ({bn_num(frames)}টি ফ্রেম পরীক্ষা করা হয়েছে)" if frames else ""

    if is_fake:
        label, confidence = "AI_GENERATED", fake_prob
        en = (f"Signs of AI generation or manipulation were found in this {what_en}{frames_en}. "
              "Don't forward it until you have checked the original source.")
        bn = (f"এই {what_bn} এআই দিয়ে তৈরি বা কারসাজির লক্ষণ পাওয়া গেছে{frames_bn}। "
              "মূল উৎস যাচাই না করে শেয়ার করবেন না।")
    else:
        label, confidence = "LIKELY_AUTHENTIC", 1 - fake_prob
        en = (f"No strong signs of AI generation were found in this {what_en}{frames_en}. "
              "This is not a guarantee: a real photo can still be shared with a false caption.")
        bn = (f"এই {what_bn} এআই দিয়ে তৈরির জোরালো কোনো লক্ষণ পাওয়া যায়নি{frames_bn}। "
              "তবে এটি শতভাগ নিশ্চয়তা নয় — আসল ছবিও ভুল ক্যাপশনে ছড়ানো হতে পারে।")

    return _payload(label, confidence, {"en": en, "bn": bn}, engine, kind=kind,
                    fake_probability=round(fake_prob, 3), frames_analyzed=frames,
                    extracted_text=extracted_text or None)


def hoax_result(entry: dict, similarity: float, extracted_text: Optional[str] = None) -> dict:
    # Scale similarity above the threshold into a 0.75–0.99 confidence band.
    span = max(1e-6, 1 - config.HOAX_THRESHOLD)
    confidence = 0.75 + 0.24 * _clip((similarity - config.HOAX_THRESHOLD) / span)
    en = f"This matches a known hoax: “{entry['claim_en']}”. {entry['fact_en']}"
    bn = f"এটি একটি পরিচিত গুজবের সাথে মিলে যায়: “{entry['claim_bn']}”। {entry['fact_bn']}"
    return _payload("KNOWN_HOAX", confidence, {"en": en, "bn": bn}, "hoax_db", kind="text",
                    matched_claim={"id": entry["id"], "claim_en": entry["claim_en"],
                                   "claim_bn": entry["claim_bn"], "similarity": round(similarity, 3)},
                    extracted_text=extracted_text or None)


def no_match_result(best_similarity: float, extracted_text: Optional[str] = None) -> dict:
    # Deliberately modest confidence: "not in our database" is not the same as "true".
    confidence = 0.6 - 0.2 * _clip(best_similarity)
    en = "No known hoax match. Verify it independently before sharing."
    bn = "পরিচিত কোনো গুজবের সাথে মিল পাওয়া যায়নি — শেয়ার করার আগে নিজে যাচাই করুন।"
    return _payload("NO_KNOWN_MATCH", confidence, {"en": en, "bn": bn}, "hoax_db", kind="text",
                    extracted_text=extracted_text or None)
