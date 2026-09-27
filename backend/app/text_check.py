"""Claim pipeline: clean OCR'd / pasted text → match against the hoax database → bilingual verdict."""
import re
import unicodedata

from . import config, explain, hoax_matcher


def _nfc(s: str) -> str:
    # Bengali has two encodings for letters like য়; OCR and keyboards disagree, so normalise everywhere.
    return unicodedata.normalize("NFC", s).replace("‌", "").replace("‍", "")


# Lines that are pure social-media UI chrome (compared after lowercasing and stripping punctuation).
_CHROME_LINES = {_nfc(s) for s in {
    "like", "comment", "share", "reply", "follow", "following", "sponsored", "see more", "see translation",
    "write a comment", "most relevant", "all comments", "view more comments", "just now", "yesterday",
    "edited", "public", "forwarded", "forwarded many times", "send message", "message", "top fan", "author",
    "লাইক", "কমেন্ট", "মন্তব্য", "শেয়ার", "উত্তর", "ফলো", "আরও দেখুন", "অনুবাদ দেখুন", "স্পনসরড",
    "ফরওয়ার্ড করা হয়েছে", "মন্তব্য লিখুন", "গতকাল", "এইমাত্র",
}}
_INLINE_NOISE = [
    re.compile(r"https?://\S+|www\.\S+", re.I),                                   # links
    re.compile(r"(?<!\w)[@#][\w.]+"),                                               # @handles / #tags
    re.compile(r"\b\d{1,2}[:.]\d{2}\s*(?:[ap]\.?\s?m\.?)?(?!\d)", re.I),            # 10:45 pm
    re.compile(r"[০-৯]{1,2}:[০-৯]{2}"),                                             # ১০:৪৫
    re.compile(r"\b\d+(?:[.,]\d+)?\s*[km]?\s*(?:likes?|comments?|shares?|reactions?|views?)\b", re.I),
    re.compile(r"\b\d+\s*(?:mins?|hrs?|hours?|days?|weeks?|[mhdw])\s*(?:ago)?\b(?=\s*[·•]|\s*$)", re.I),
    re.compile(r"\b\d{1,3}\s?%"),                                                   # battery
    re.compile(r"[·•|]+"),
]
_LETTERS = re.compile(r"[A-Za-zঀ-৿]")


def clean_ocr_text(text: str) -> str:
    kept = []
    for line in _nfc(text or "").splitlines():
        for pattern in _INLINE_NOISE:
            line = pattern.sub(" ", line)
        line = re.sub(r"\s+", " ", line).strip()
        bare = re.sub(r"[^\wঀ-৿ ]+", "", line).strip().lower()
        if len(_LETTERS.findall(line)) < 3 or bare in _CHROME_LINES:
            continue
        kept.append(line)
    return " ".join(kept)


def is_text_heavy(cleaned: str) -> bool:
    """A photo with a caption or sign isn't a claim; a screenshot of a post is."""
    words = re.findall(r"[A-Za-zঀ-৿]{2,}", cleaned)
    return len(words) >= 6 and len(_LETTERS.findall(cleaned)) >= 25


def check_claim(text: str, extracted: bool = False) -> dict:
    text = re.sub(r"\s+", " ", text).strip()
    match = hoax_matcher.best_match(text)
    shown = text[:500] if extracted else None
    if match and match.score >= config.HOAX_THRESHOLD:
        return explain.hoax_result(match.entry, match.score, extracted_text=shown)
    return explain.no_match_result(match.score if match else 0.0, extracted_text=shown)


def fallback_claim() -> dict:
    return explain.no_match_result(0.0)
