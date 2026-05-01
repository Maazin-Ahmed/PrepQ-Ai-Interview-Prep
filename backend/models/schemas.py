from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime


# ─────────────────────────────────────────────
# REQUEST MODELS
# ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be blank or whitespace only.")
        return v.strip()


class OnboardingAnswers(BaseModel):
    company: Optional[str] = Field(None, max_length=200)
    role: Optional[str] = Field(None, max_length=200)
    days_left: int = Field(default=30, ge=1, le=365)
    round: Optional[Literal[
        "online_assessment",
        "technical",
        "hr",
        "case_study",
        "managerial",
        "system_design",
    ]] = None
    level: Optional[Literal["beginner", "some_experience", "confident"]] = None
    prepared: Optional[str] = Field(None, max_length=2000)
    skipped: Optional[str] = Field(None, max_length=2000)
    mode: Optional[Literal["interview_prep", "upskill", "shortlist"]] = "interview_prep"


class PlanRequest(BaseModel):
    session_id: Optional[str] = None
    onboarding: OnboardingAnswers


class MockScoreRequest(BaseModel):
    session_id: str
    question: str = Field(..., min_length=1, max_length=2000)
    answer: str = Field(..., min_length=1, max_length=5000)
    question_index: int = Field(..., ge=0)


class MockQuestionRequest(BaseModel):
    session_id: str
    question_index: int = Field(default=0, ge=0)


# ─────────────────────────────────────────────
# RESPONSE MODELS
# ─────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    version: str = "1.0.0"


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    company: Optional[str]
    role: Optional[str]
    days_left: Optional[int]
    round: Optional[str]
    level: Optional[str]
    created_at: datetime


class MessageRecord(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class TierItem(BaseModel):
    topic: str
    reason: str
    resources: Optional[list[str]] = []


class DailyTask(BaseModel):
    day: int
    focus: str
    tasks: list[str]


class PrepPlanData(BaseModel):
    session_id: str
    company: str
    role: str
    days_left: int
    round: str
    tier1: list[TierItem]
    tier2: list[TierItem]
    tier3: list[TierItem]
    daily_breakdown: list[DailyTask]
    red_flags: list[str]
    mock_question: str
    created_at: datetime


class MockScoreResult(BaseModel):
    question: str
    answer: str
    clarity: int = Field(..., ge=1, le=5)
    correctness: int = Field(..., ge=1, le=5)
    depth: int = Field(..., ge=1, le=5)
    overall: float
    feedback: str
    missing: list[str]
    next_question: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    code: int


# ─────────────────────────────────────────────
# INTERNAL MODELS
# ─────────────────────────────────────────────

class UserSession(BaseModel):
    session_id: str
    user_id: str
    company: Optional[str] = None
    role: Optional[str] = None
    days_left: Optional[int] = None
    round: Optional[str] = None
    level: Optional[str] = None
    onboarding_complete: bool = False
    message_count: int = 0


class StreamChunk(BaseModel):
    type: Literal["chunk", "done", "error", "metadata"]
    text: Optional[str] = None
    session_id: Optional[str] = None
    error: Optional[str] = None
