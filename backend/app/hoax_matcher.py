"""Bilingual fuzzy matching against the curated hoax database (data/hoaxes.json).

Score = max of:
  * token coverage: share of a claim's meaningful words found in the input (tolerates extra text around the
    claim, Bengali inflections via prefix match, and OCR typos via rapidfuzz ratio ≥ 85)
  * whole-string rapidfuzz ratio, only when ≥ 0.8 (near-verbatim copies)
  * optional multilingual sentence-embedding cosine (ENABLE_EMBEDDINGS=1) for paraphrases/cross-language
"""
import json
import logging
import math
import re
import threading
import unicodedata
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz, process

from . import config

log = logging.getLogger(__name__)

HOAX_FILE = config.DATA_DIR / "hoaxes.json"
_TOKEN = re.compile(r"[a-z0-9]+|[ঀ-৿]+")
_STOP = {
    # en
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "in", "on", "at", "for", "and", "or",
    "it", "its", "this", "that", "these", "those", "with", "by", "from", "as", "will", "can", "you", "your",
    "has", "have", "had", "not", "no", "do", "does", "if", "all", "any", "our", "we", "they", "their", "he",
    "she", "his", "her", "them", "so", "than", "then", "there", "who", "what", "which", "into", "out", "up",
    # bn
    "এবং", "ও", "যে", "এই", "একটি", "করে", "হয়", "না", "কি", "কী", "থেকে", "জন্য", "সাথে", "সঙ্গে", "তার",
    "আর", "হবে", "হয়েছে", "করা", "দিয়ে", "এর", "তা", "সে", "তারা", "আমরা", "আপনি", "আপনার", "কোনো", "বা",
    "এক", "যা", "হলে", "নেই", "আছে", "এটা", "এটি", "ওই", "সব", "কিন্তু", "তবে", "করতে", "হচ্ছে", "দেওয়া",
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("‌", "").replace("‍", "")
    return text.lower()


_STOP = {_normalize(w) for w in _STOP}


_SYNONYMS = {"tk": "taka", "taka": "taka", "টাকার": "টাকা", "covid19": "covid", "govt": "government"}


def _stem(token: str) -> str:
    """Tiny English stemmer. It only needs to be consistent, not correct: charging/charges/charge → charg.
    Bengali inflections are handled by prefix matching instead."""
    if len(token) <= 3 or not (token.isascii() and token.isalpha()):
        return token
    for suffix in ("ing", "ed"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    if token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    if token.endswith("e") and len(token) > 3:
        token = token[:-1]
    return token


def _tokens(text: str) -> list[str]:
    return [_stem(_SYNONYMS.get(t, t)) for t in _TOKEN.findall(_normalize(text)) if len(t) >= 2 and t not in _STOP]


@dataclass
class Candidate:
    entry: dict
    text: str
    norm: str
    tokens: list[str]


@dataclass
class Match:
    entry: dict
    score: float
    matched_text: str


_lock = threading.Lock()
_entries: list[dict] = []
_candidates: list[Candidate] = []
_idf: dict[str, float] = {}
_max_idf = 1.0
_embedder = None
_cand_embeddings = None


def _load():
    global _entries, _max_idf
    with _lock:
        if _entries:
            return
        _entries = json.loads(HOAX_FILE.read_text(encoding="utf-8"))
        doc_freq: dict[str, int] = {}
        for e in _entries:
            entry_tokens = set()
            for text in [e["claim_en"], e["claim_bn"], *e.get("aliases", [])]:
                cand = Candidate(e, text, _normalize(text), _tokens(text))
                _candidates.append(cand)
                entry_tokens.update(cand.tokens)
            for t in entry_tokens:
                doc_freq[t] = doc_freq.get(t, 0) + 1
        # Rare words ("microchip", "থানকুনি") are what identify a hoax; common ones ("money", "করোনা") less so.
        _max_idf = math.log(1 + len(_entries))
        _idf.update({t: math.log(1 + len(_entries) / df) for t, df in doc_freq.items()})
        log.info("hoax db: %d claims, %d match strings", len(_entries), len(_candidates))
        if config.ENABLE_EMBEDDINGS:
            _load_embedder()


def _load_embedder():
    global _embedder, _cand_embeddings
    try:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(config.EMBED_MODEL_ID, device="cpu")
        _cand_embeddings = _embedder.encode([c.text for c in _candidates], normalize_embeddings=True)
    except Exception as exc:
        _embedder = None
        log.warning("embeddings disabled: %r", exc)


def entries() -> list[dict]:
    _load()
    return _entries


def entry_by_id(hoax_id: str) -> Optional[dict]:
    return next((e for e in entries() if e["id"] == hoax_id), None)


def status() -> dict:
    _load()
    return {"entries": len(_entries), "match_strings": len(_candidates), "embeddings": _embedder is not None}


def _hit(token: str, pool_set: set, pool: list[str]) -> bool:
    if token in pool_set:
        return True
    if len(token) >= 3 and any(p.startswith(token) for p in pool):  # সেতু → সেতুতে, vaccine → vaccines
        return True
    return len(token) >= 4 and process.extractOne(token, pool, scorer=fuzz.ratio, score_cutoff=85) is not None


def _weight(token: str) -> float:
    return _idf.get(token, _max_idf)  # words absent from the DB count as maximally specific


def _coverage(tokens: list[str], pool_set: set, pool: list[str]) -> float:
    total = sum(_weight(t) for t in tokens)
    return sum(_weight(t) for t in tokens if _hit(t, pool_set, pool)) / total if total else 0.0


def _lexical_score(q_tokens: list[str], q_set: set, q_norm: str, cand: Candidate) -> float:
    if not cand.tokens or not q_tokens:
        return 0.0
    cov_claim = _coverage(cand.tokens, q_set, q_tokens)
    score = cov_claim
    if len(q_tokens) >= 3:  # very short inputs ("coronavirus") must not match on a single shared word
        cov_query = _coverage(q_tokens, set(cand.tokens), cand.tokens)
        score = max(score, (cov_claim + cov_query) / 2)
    # Whole-string similarity only helps for near-verbatim copies with OCR typos; below 0.8 it's just noise
    # (unrelated sentences of similar length already score 0.5–0.6).
    length_ratio = len(q_norm) / max(1, len(cand.norm))
    if 0.7 <= length_ratio <= 1.4:
        ratio = fuzz.ratio(q_norm, cand.norm) / 100
        if ratio >= 0.8:
            score = max(score, ratio)
    return score


def best_match(text: str) -> Optional[Match]:
    _load()
    q_norm = _normalize(text)
    q_tokens = _tokens(text)
    if not q_tokens:
        return None
    q_set = set(q_tokens)

    scores = [_lexical_score(q_tokens, q_set, q_norm, c) for c in _candidates]

    if _embedder is not None:
        # Long OCR text: embed each sentence separately so the claim isn't diluted by surrounding text.
        parts = [p for p in re.split(r"[.!?।\n]+", text) if len(p.strip()) > 8][:20] or [text]
        q_emb = _embedder.encode(parts + [text], normalize_embeddings=True)
        cos = (q_emb @ _cand_embeddings.T).max(axis=0)
        scores = [max(s, float(c)) for s, c in zip(scores, cos)]

    best = max(range(len(scores)), key=scores.__getitem__)
    return Match(_candidates[best].entry, round(float(scores[best]), 3), _candidates[best].text)
