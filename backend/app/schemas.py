from typing import Literal, Optional

from pydantic import BaseModel, Field


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


class JobCreated(BaseModel):
    job_id: str
    status: Literal["pending", "done", "error"] = "pending"
    poll_after_ms: int = 1500


class Bilingual(BaseModel):
    en: str
    bn: str


class MatchedClaim(BaseModel):
    id: str
    claim_en: str
    claim_bn: str
    similarity: float


class Result(BaseModel):
    job_id: str
    status: Literal["pending", "done", "error"]
    kind: Optional[Literal["image", "video", "text"]] = None
    verdict: Optional[Literal["red", "green"]] = None
    label: Optional[Literal["AI_GENERATED", "LIKELY_AUTHENTIC", "KNOWN_HOAX", "NO_KNOWN_MATCH"]] = None
    confidence: Optional[float] = None
    fake_probability: Optional[float] = None
    title: Optional[Bilingual] = None
    explanation: Optional[Bilingual] = None
    engine: Optional[str] = None
    frames_analyzed: Optional[int] = None
    matched_claim: Optional[MatchedClaim] = None
    extracted_text: Optional[str] = None
    elapsed_ms: Optional[int] = None
